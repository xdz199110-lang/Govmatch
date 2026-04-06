import os
import re
import time
import logging
import requests
import psycopg2
from psycopg2.extras import Json, execute_values
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- 统一 logging 配置 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- 数据库配置（从环境变量读取）---
def _build_db_config() -> dict:
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("必须设置 DB_PASSWORD 或 DATABASE_URL 环境变量")
        m = re.match(
            r"(?:postgres|postgresql)://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<dbname>.+)",
            db_url,
        )
        if not m:
            raise ValueError("DATABASE_URL 格式不正确")
        return m.groupdict()
    return {
        "dbname": os.getenv("DB_NAME", "govmatch"),
        "user": os.getenv("DB_USER", "api_user"),
        "password": db_password,
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
    }


DB_CONFIG = _build_db_config()

# API 配置
API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DAYS_BACK = int(os.getenv("DAYS_BACK", 7))


def fetch_page(page: int, start_date: str, end_date: str, retries: int = 3):
    """获取一页数据，带重试"""
    payload = {
        "filters": {
            "award_type_codes": ["A"],
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Action Date", "Start Date", "generated_internal_id"],
        "sort": "Start Date",
        "order": "desc",
        "limit": 100,
        "page": page,
    }
    for attempt in range(retries):
        try:
            resp = requests.post(API_URL, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = 2**attempt
                logger.warning("API 限流（429），等待 %ds（第 %d 次重试）", wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning("请求超时（第 %d/%d 次），page=%d", attempt + 1, retries, page)
            time.sleep(2**attempt)
        except requests.exceptions.ConnectionError as e:
            logger.warning("网络连接失败（第 %d/%d 次）: %s", attempt + 1, retries, e)
            time.sleep(2**attempt)
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP 请求错误（第 %d/%d 次）: %s", attempt + 1, retries, e)
            return None
        except Exception:
            logger.exception("fetch_page page=%d 发生未知异常", page)
            time.sleep(2**attempt)
    logger.error("fetch_page page=%d 重试 %d 次后失败", page, retries)
    return None


def main():
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
    logger.info("开始拉取数据，日期范围: %s 至 %s", start_date, end_date)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("数据库连接成功 [%s:%s/%s]",
                    DB_CONFIG["host"], DB_CONFIG["port"], DB_CONFIG["dbname"])
    except psycopg2.OperationalError as e:
        logger.exception("数据库连接失败 [%s:%s]", DB_CONFIG["host"], DB_CONFIG["port"])
        return
    except Exception as e:
        logger.exception("数据库连接未知错误")
        return

    cur = conn.cursor()
    page = 1
    total_inserted = 0
    consecutive_empty_pages = 0
    max_empty_pages_before_exit = 2

    try:
        while True:
            data = fetch_page(page, start_date, end_date)
            if data is None:
                logger.warning("Page %d 获取失败（重试耗尽），中止拉取", page)
                break

            results = data.get("results", [])
            if not results:
                consecutive_empty_pages += 1
                logger.info("Page %d 无数据（第 %d 次连续空页）", page, consecutive_empty_pages)
                if consecutive_empty_pages >= max_empty_pages_before_exit:
                    logger.info("连续空页达到上限（%d），退出循环", max_empty_pages_before_exit)
                    break
                page += 1
                time.sleep(1)
                continue

            consecutive_empty_pages = 0

            new_rows = []
            for row in results:
                award_id = row.get("Award ID")
                if not award_id:
                    continue
                recipient_name = row.get("Recipient Name")
                award_amount = row.get("Award Amount")
                action_date = row.get("Action Date")
                start_date_val = row.get("Start Date")
                internal_id = row.get("generated_internal_id")
                raw_json = row

                def parse_date(d):
                    if d and d != "null":
                        return d
                    return None

                new_rows.append(
                    (
                        award_id,
                        recipient_name,
                        award_amount,
                        parse_date(action_date),
                        parse_date(start_date_val),
                        internal_id,
                        Json(raw_json),
                    )
                )

            if not new_rows:
                page += 1
                time.sleep(0.5)
                continue

            insert_sql = """
                INSERT INTO contracts (award_id, recipient_name, award_amount, action_date, start_date, internal_id, raw_data)
                VALUES %s
                ON CONFLICT (award_id) DO NOTHING
            """
            try:
                execute_values(cur, insert_sql, new_rows, page_size=100)
                conn.commit()
                total_inserted += len(new_rows)
                logger.info("Page %d: 插入 %d 条新记录（累计 %d）", page, len(new_rows), total_inserted)
            except psycopg2.Error as e:
                logger.exception("插入数据库失败，page=%d", page)
                conn.rollback()
            except Exception as e:
                logger.exception("插入时发生未知错误，page=%d", page)
                conn.rollback()

            page += 1
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.warning("用户中断，保存当前进度（已插入 %d 条）", total_inserted)
        conn.rollback()
    except Exception:
        logger.exception("主循环发生未捕获异常")
    finally:
        try:
            cur.close()
            conn.close()
            logger.info("数据库连接已关闭")
        except Exception:
            pass

    logger.info("任务完成，共插入 %d 条新合同记录", total_inserted)


if __name__ == "__main__":
    main()

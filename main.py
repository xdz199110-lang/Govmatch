from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import Error as PgError
import logging
import os
from urllib.parse import urlparse, unquote
from datetime import date, datetime, timedelta
from pydantic import BaseModel
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
def _build_db_config() -> Optional[dict]:
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            logger.error("缺少数据库配置：既未设置 DB_PASSWORD，也未设置 DATABASE_URL 环境变量")
            return None
        try:
            parsed = urlparse(db_url)
            scheme = parsed.scheme.lower()
            if scheme not in ("postgresql", "postgres"):
                logger.error(
                    "DATABASE_URL 协议不支持（仅支持 postgresql:// 和 postgres://）：%s",
                    scheme,
                )
                return None
            user = unquote(parsed.username or "")
            password = unquote(parsed.password or "")
            host = parsed.hostname or ""
            port = parsed.port or 5432
            dbname = parsed.path.lstrip("/") if parsed.path else ""
            if not all([user, password, host, dbname]):
                logger.error(
                    "DATABASE_URL 格式不完整，解析结果缺失必要字段 "
                    "（user=%s, password=%s, host=%s, dbname=%s）",
                    user, "***" if password else "", host, dbname,
                )
                return None
            result = {
                "user": user,
                "password": password,
                "host": host,
                "port": port,
                "dbname": dbname,
            }
            logger.info("DATABASE_URL 解析成功：%s@%s:%s/%s",
                        user, host, port, dbname)
            return result
        except Exception as e:
            logger.error("DATABASE_URL 解析异常：%s | URL=%.80s...", e, db_url)
            return None
    return {
        "dbname": os.getenv("DB_NAME", "govmatch"),
        "user": os.getenv("DB_USER", "api_user"),
        "password": db_password,
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
    }


def _get_db_config_fallback() -> dict:
    return {
        "dbname": os.getenv("DB_NAME", "govmatch"),
        "user": os.getenv("DB_USER", "api_user"),
        "password": os.getenv("DB_PASSWORD", ""),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
    }


_db_config_parsed = _build_db_config()
if _db_config_parsed is not None:
    DB_CONFIG = _db_config_parsed
    logger.info("数据库配置加载成功（来自 DATABASE_URL）")
else:
    DB_CONFIG = _get_db_config_fallback()
    logger.warning("DATABASE_URL 解析失败，已回退到从环境变量逐项读取")

app = FastAPI(title="GovMatch API", description="Federal Contract Search API", version="1.0")

# ── CORS 中间件（插入位置）──────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://govmatch-frontend.onrender.com",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ── CORS 结束 ──────────────────────────

logger.info("GovMatch API 启动，数据库: %s:%s/%s",
            DB_CONFIG["host"], DB_CONFIG["port"], DB_CONFIG["dbname"])

# 响应模型
class ContractResponse(BaseModel):
    award_id: str
    recipient_name: Optional[str]
    award_amount: Optional[float]
    action_date: Optional[date]
    start_date: Optional[date]
    internal_id: Optional[str]


@app.get("/contracts/search", response_model=List[ContractResponse])
def search_contracts(
    recipient_name: Optional[str] = Query(None, description="企业名称（模糊匹配）"),
    min_amount: Optional[float] = Query(None, description="最小金额"),
    max_amount: Optional[float] = Query(None, description="最大金额"),
    start_date_from: Optional[date] = Query(None, description="起始日期（YYYY-MM-DD）"),
    start_date_to: Optional[date] = Query(None, description="结束日期（YYYY-MM-DD）"),
    sort_by: str = Query("start_date", description="排序字段: start_date, award_amount"),
    order: str = Query("desc", description="排序方向: asc, desc"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
) -> List[ContractResponse]:
    """
    搜索联邦合同
    """
    # 构建查询条件
    conditions = []
    params = []

    if recipient_name:
        conditions.append("recipient_name ILIKE %s")
        params.append(f"%{recipient_name}%")

    if min_amount is not None:
        conditions.append("award_amount >= %s")
        params.append(min_amount)

    if max_amount is not None:
        conditions.append("award_amount <= %s")
        params.append(max_amount)

    if start_date_from:
        conditions.append("start_date >= %s")
        params.append(start_date_from)

    if start_date_to:
        conditions.append("start_date <= %s")
        params.append(start_date_to)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    # 排序方向
    sort_order = "DESC" if order.lower() == "desc" else "ASC"
    # 确保排序字段合法
    if sort_by not in ["start_date", "award_amount"]:
        sort_by = "start_date"

    # 分页偏移
    offset = (page - 1) * limit

    # 查询总数（用于分页元数据，可选）
    count_sql = f"SELECT COUNT(*) FROM contracts WHERE {where_clause}"
    # 查询数据
    data_sql = f"""
        SELECT award_id, recipient_name, award_amount, action_date, start_date, internal_id
        FROM contracts
        WHERE {where_clause}
        ORDER BY {sort_by} {sort_order}
        LIMIT %s OFFSET %s
    """

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except PgError as e:
        logger.exception("数据库连接失败 [%s:%s]", DB_CONFIG["host"], DB_CONFIG["port"])
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as e:
        logger.exception("未知错误（数据库连接阶段）")
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        # 获取总数
        cur.execute(count_sql, params)
        total = cur.fetchone()["count"]

        # 获取数据
        cur.execute(data_sql, params + [limit, offset])
        rows = cur.fetchall()
    except PgError as e:
        logger.exception("数据库查询失败，SQL: %s | 参数: %s", count_sql[:80], params)
        raise HTTPException(status_code=500, detail="Database query error")
    except Exception as e:
        logger.exception("未知错误（查询阶段）")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

    return rows


@app.get("/")
def root():
    return {"message": "GovMatch API is running. Try /contracts/search?recipient_name=SAFEWARE"}


@app.get("/recipient/predict/{recipient_name}")
def predict_win_probability(
    recipient_name: str,
    lookback_days: int = Query(default=365, ge=1, le=3650),
):
    """
    根据企业历史合同数据，预测中标概率和竞争力得分
    """
    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).date()

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except PgError as e:
        logger.exception("数据库连接失败 [%s]", DB_CONFIG["host"])
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as e:
        logger.exception("未知错误（数据库连接阶段）")
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        cur.execute(
            """
            SELECT award_amount, start_date
            FROM contracts
            WHERE recipient_name ILIKE %s
            """,
            (recipient_name,),
        )
        rows = cur.fetchall()

        if not rows:
            return {
                "recipient_name": recipient_name,
                "total_contracts": 0,
                "total_amount": 0.0,
                "avg_amount": 0.0,
                "recent_activity": False,
                "win_rate_score": 0.0,
                "predicted_win_probability": 0.05,
                "confidence": "Low (no data)",
            }

        total_contracts = len(rows)
        total_amount = sum(row["award_amount"] or 0 for row in rows)
        avg_amount = total_amount / total_contracts if total_contracts > 0 else 0
        recent_contracts = [
            r for r in rows if r["start_date"] and r["start_date"] >= cutoff_date
        ]
        recent_activity = len(recent_contracts) > 0

        def normalize_log(value, max_expected=1000, min_val=1):
            if value <= 0:
                return 0
            import math
            return min(1.0, math.log(value + 1) / math.log(max_expected + 1))

        count_score = normalize_log(total_contracts, max_expected=500)
        amount_score = normalize_log(total_amount, max_expected=1e8)
        avg_amount_score = normalize_log(avg_amount, max_expected=1e6)
        activity_score = 1.0 if recent_activity else 0.0

        win_rate_score = (
            0.4 * count_score
            + 0.3 * amount_score
            + 0.2 * avg_amount_score
            + 0.1 * activity_score
        ) * 100

        predicted_prob = 0.05 + (win_rate_score / 100) * 0.9
        predicted_prob = round(predicted_prob, 2)

        if total_contracts >= 20:
            confidence = "High"
        elif total_contracts >= 5:
            confidence = "Medium"
        else:
            confidence = "Low"

        return {
            "recipient_name": recipient_name,
            "total_contracts": total_contracts,
            "total_amount": round(total_amount, 2),
            "avg_amount": round(avg_amount, 2),
            "recent_activity": recent_activity,
            "win_rate_score": round(win_rate_score, 1),
            "predicted_win_probability": predicted_prob,
            "confidence": confidence,
        }

    except PgError as e:
        logger.exception("数据库查询失败，受援企业: %s", recipient_name)
        raise HTTPException(status_code=500, detail="Database query error")
    except Exception as e:
        logger.exception("未知错误（查询阶段）")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

import requests
import json

url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
payload = {
    "filters": {
        "award_type_codes": ["A"],
        "time_period": [{"start_date": "2025-10-01", "end_date": "2026-03-31"}]
    },
    "fields": ["Award ID", "Recipient Name", "Award Amount", "Action Date", "Start Date"],
    "sort": "Start Date",
    "order": "desc",
    "limit": 5
}

resp = requests.post(url, json=payload)
print(f"HTTP状态码: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print("成功获取到数据，前5条记录：")
    results = data.get("results", [])
    if results:
        print(json.dumps(results, indent=2))
        print("\n第一条记录包含的字段：", list(results[0].keys()))
    else:
        print("没有数据")
else:
    print("失败，错误信息：", resp.text)
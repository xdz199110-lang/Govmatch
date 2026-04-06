import requests
import time

url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
payload = {
    "filters": {
        "award_type_codes": ["A"],
        "time_period": [{"start_date": "2025-10-01", "end_date": "2026-03-31"}]
    },
    "fields": ["Award ID", "Recipient Name", "Award Amount", "Start Date"],
    "limit": 1
}

for i in range(30):
    resp = requests.post(url, json=payload)
    print(f"Request {i+1}: {resp.status_code}")
    if resp.status_code == 429:
        print("Rate limit hit! Waiting 2 seconds...")
        time.sleep(2)
    else:
        time.sleep(0.2)  # 模拟正常请求间隔
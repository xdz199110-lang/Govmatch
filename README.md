# GovMatch — Federal Contract Search & Win Rate Prediction API

**Live Demo:** https://govmatch-frontend.onrender.com

**API Base:** https://govmatch-api.onrender.com

**Swagger Docs:** https://govmatch-api.onrender.com/docs

---

## About

GovMatch is a data API that indexes U.S. federal contract awards and provides a win-rate prediction score for any recipient company. It pulls raw records from [USAspending.gov](https://www.usaspending.gov) and exposes them via a FastAPI backend backed by PostgreSQL.

**Who it's for:** Indie hackers, small biz dev agencies, and govcon consultants who want a programmatic way to research federal contract history for a given company.

---

## Features

- **Contract Search** — Full-text search across millions of federal award records by company name, dollar range, and date window
- **Win Rate Prediction** — Scores a company's competitiveness (0–100) based on contract count, total volume, average deal size, and recent activity
- **Paginated Results** — Up to 100 records per page with `page` / `limit` parameters
- **Sort & Filter** — Sort by `start_date` or `award_amount`, in `asc` or `desc` order
- **Auto-refresh Cron Job** — Database is periodically re-seeded from the USAspending.gov API
- **No frontend required** — Pure REST API; use it from any client

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.115 / Uvicorn |
| Database | PostgreSQL (Render Cloud) |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Data Source | USAspending.gov REST API |
| Hosting | Render (web services + cron) |

---

## API Endpoints

### `GET /contracts/search`

Search federal contract records.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `recipient_name` | string | — | Company name (case-insensitive, partial match) |
| `min_amount` | float | — | Minimum award amount ($) |
| `max_amount` | float | — | Maximum award amount ($) |
| `start_date_from` | date | — | Contracts starting on or after this date (`YYYY-MM-DD`) |
| `start_date_to` | date | — | Contracts starting on or before this date (`YYYY-MM-DD`) |
| `sort_by` | string | `start_date` | Sort field: `start_date` or `award_amount` |
| `order` | string | `desc` | Sort direction: `asc` or `desc` |
| `page` | int | `1` | Page number (1-based) |
| `limit` | int | `20` | Records per page (max 100) |

**Example:**

```
GET https://govmatch-api.onrender.com/contracts/search?recipient_name=SAFEWARE&limit=5
```

**Response:**

```json
[
  {
    "award_id": "FA8806-23-C-0004",
    "recipient_name": "SAFEWARE INC",
    "award_amount": 1245000.0,
    "action_date": "2023-04-15",
    "start_date": "2023-05-01",
    "internal_id": "N/A"
  }
]
```

---

### `GET /recipient/predict/{recipient_name}`

Returns a win-rate prediction and company profile for a given recipient.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `recipient_name` | path (string) | — | Company name to look up |
| `lookback_days` | query (int) | `365` | How many days of history to analyze (max 3650) |

**Example:**

```
GET https://govmatch-api.onrender.com/recipient/predict/SAFEWARE?lookback_days=730
```

**Response:**

```json
{
  "recipient_name": "SAFEWARE",
  "total_contracts": 12,
  "total_amount": 8400000.0,
  "avg_amount": 700000.0,
  "recent_activity": true,
  "win_rate_score": 74.3,
  "predicted_win_probability": 0.72,
  "confidence": "High"
}
```

**Score logic:**

| Component | Weight | Description |
|---|---|---|
| Contract count | 40% | Log-normalized total number of awards |
| Total amount | 30% | Log-normalized sum of all award dollars |
| Avg deal size | 20% | Log-normalized average award |
| Recent activity | 10% | Binary: any award in the lookback window? |

---

### `GET /`

Health check.

```
GET https://govmatch-api.onrender.com/
```

Returns:

```json
{"message": "GovMatch API is running. Try /contracts/search?recipient_name=SAFEWARE"}
```

---

## Local Development

### Prerequisites

- Python 3.10+
- A local PostgreSQL instance (or a cloud DB you can connect to)

### 1. Clone & set up virtual environment

```bash
git clone <your-repo-url>
cd govmatch
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your database credentials:

```env
# Option A: Full DATABASE_URL (recommended for local dev)
DATABASE_URL=postgres://api_user:your_password@localhost:5432/govmatch

# Option B: Individual fields (fallback if DATABASE_URL is absent)
DB_PASSWORD=your_password
DB_NAME=govmatch
DB_USER=api_user
DB_HOST=localhost
DB_PORT=5432
```

### 4. Initialize the database schema

Connect to your PostgreSQL database and run the schema script:

```bash
psql "postgres://api_user:your_password@localhost:5432/govmatch" -f create_table.sql
```

### 5. (Optional) Seed initial data

If you want a small test dataset without running the full cron job, run `fetch_contracts.py` manually:

```bash
DAYS_BACK=30 python fetch_contracts.py
```

### 6. Start the API server

```bash
python main.py
# or, with hot reload:
uvicorn main:app --reload --port 8000
```

The API will be available at **http://localhost:8000**.

Swagger docs: **http://localhost:8000/docs**

### 7. Run the frontend (optional)

Open `frontend/index.html` directly in a browser — it auto-detects localhost vs production and routes API calls accordingly. No build step required.

For a proper local dev server for the frontend:

```bash
cd frontend
python -m http.server 3000
# → http://localhost:3000
```

---

## Data Source

All contract data is pulled from the U.S. Treasury's [USAspending.gov API](https://api.usaspending.gov) (official federal spending data, updated daily). Data is stored locally in PostgreSQL and refreshed via a nightly cron job that calls the USAspending REST API.

Fields stored:

| Database Column | USAspending Source Field |
|---|---|
| `award_id` | `award_id_piid` |
| `recipient_name` | `recipient_name` |
| `award_amount` | `award_amount` |
| `action_date` | `action_date` |
| `start_date` | `period_of_performance_start_date` |
| `internal_id` | `parent_award_id` or `N/A` |

---

## Project Structure

```
govmatch/
├── main.py              # FastAPI app (all routes, DB logic)
├── fetch_contracts.py   # USAspending.gov data fetcher (cron job script)
├── create_table.sql     # PostgreSQL schema for contracts table
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── render.yaml          # Render deployment config (frontend)
├── frontend/
│   ├── index.html       # Demo page
│   ├── style.css        # Styles
│   └── script.js        # API calls, rendering, pagination
└── README.md
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes* | Full PostgreSQL connection string |
| `DB_PASSWORD` | Yes* | PostgreSQL password (used if `DATABASE_URL` absent) |
| `DB_NAME` | No | Database name (default: `govmatch`) |
| `DB_USER` | No | Database user (default: `api_user`) |
| `DB_HOST` | No | Host (default: `localhost`) |
| `DB_PORT` | No | Port (default: `5432`) |

*\* Either `DATABASE_URL` OR `DB_PASSWORD` must be set.*

---

## Deployment

### Backend (Render)

1. Create a new **Web Service** on Render
2. Connect your GitHub repo
3. Set the following:

   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment:** `Python 3`
   - Add environment variable: `DATABASE_URL` = your Render PostgreSQL internal URL (auto-injected on free tier)

4. Deploy — the API will be live at `https://govmatch-api.onrender.com`

### Frontend (Render)

The `render.yaml` in this repo defines a static site deployment. When connected to your GitHub repo, Render will automatically deploy `frontend/` as a static site.

### Cron Job (Render)

The `fetch_contracts.py` script is designed to be run on a schedule. On Render, set up a **Cron Job** with:

- **Schedule:** `0 2 * * *` (2 AM UTC daily)
- **Command:** `python fetch_contracts.py`

---

## License

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
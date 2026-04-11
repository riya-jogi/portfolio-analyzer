# Stock Portfolio Analyzer

Production-style demo: **Django + Django REST Framework** backend (SQLite), **Streamlit** frontend. Portfolio rows are stored per user; live quotes via **yfinance** (NSE symbols default to `*.NS`); portfolio **XIRR** via **pyxirr**.

## Requirements

- Python 3.10+
- Network access for yfinance (market data)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
python manage.py migrate
```

Optional: create a Django admin superuser (email + password; the custom user uses email as the username):

```bash
python manage.py createsuperuser
```

## Run the backend

```bash
python manage.py runserver
```

Default: `http://127.0.0.1:8000`

### API routes

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/auth/register/` | No — returns `token` |
| POST | `/api/auth/login/` | No — returns `token` |
| GET | `/api/auth/me/` | Token |
| POST | `/upload/` | Token — multipart field `file` (CSV) |
| GET | `/analysis/` | Token |

Set `Authorization: Token <key>` for protected routes.

## Run the frontend (Streamlit)

In another terminal (with the same venv):

```bash
streamlit run frontend_app.py
```

Optional configuration:

- Environment variable: `API_BASE_URL` (default `http://127.0.0.1:8000`)
- Or create `.streamlit/secrets.toml` with `API_BASE_URL = "http://127.0.0.1:8000"`

## CSV format

Upload **replaces** all holdings for the logged-in user.

Required fields (after normalization): `stock_name`, `quantity`, `buy_price`, and **`buy_date` unless omitted** (see below).

**Broker exports (e.g. Zerodha “holdings” CSV):** headers like `Instrument`, `Qty.`, `Avg. cost` are recognized (`Instrument` → stock, `Qty.` → quantity, `Avg. cost` → buy price). These files usually have **no purchase date**; the app then sets **`buy_date` to today** for every row and logs a warning — add your own `buy_date` column if you need accurate XIRR.

The uploader accepts **UTF-8 or Windows (cp1252) encoding**, **comma or semicolon separators** (Excel in many regions exports `;`), **UTF-8 BOM**, **any casing**, **spaces instead of underscores** (e.g. `Stock Name`, `Buy Date`), and common aliases (`Symbol`, `Ticker`, `Qty`, `Price`, `Date`, etc.). Save as CSV from Excel when possible.

```csv
stock_name,quantity,buy_price,buy_date
RELIANCE,10,2450.50,2024-01-15
TCS,5,3500,2023-06-01
```

- `buy_date`: parsed with day-first preference (e.g. `15/01/2024` or ISO `2024-01-15`).
- Symbols without a suffix are treated as **NSE** tickers (`RELIANCE` → `RELIANCE.NS`). Use `*.BO` for BSE if needed.

## Analysis semantics

- **Total investment**: sum of `quantity * buy_price` for all rows.
- **Current value**: sum of `quantity * last_price` only for rows where a live price was fetched; missing quotes are excluded from this sum (see `priced_holdings_count` vs `total_holdings_count`).
- **XIRR**: computed when **every** holding has a live price; otherwise `xirr` is `null` and `xirr_error` explains why.

## Troubleshooting CSV upload

When `/upload/` fails, open the **same terminal where `runserver` is running**. Logs use the **`portfolio`** logger (e.g. `portfolio.upload`) and include:

- Encoding used (`utf-8-sig`, `cp1252`, …), byte size, and a **preview of the first line**
- Each **parse attempt** (separator + engine) and resulting column headers
- **Column rename / alias** mapping after normalization
- Errors for **missing columns** or **row validation**

With `DEBUG = True`, failed parse attempts also emit **DEBUG** lines with stack traces. The JSON error for “Could not parse CSV” may include `repr(exception)` in the response when `DEBUG` is on.

## Production notes

- Change `SECRET_KEY` and set `DEBUG = False` in `portfolio_analyzer/settings.py` (or use environment variables).
- Use a production WSGI server and HTTPS behind a reverse proxy.

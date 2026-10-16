# Zipaworld Rate Radar

**Zipaworld Rate Radar** is an enterprise-grade, live, API-driven freight rate-expiry and carrier-depth coverage analytics platform. It automatically calculates tariff validity, tracks impending expirations across configurable time horizons, detects corridor resilience gaps, and provides operational action directives for freight procurement teams—without requiring manual file imports.

---

## Key Features

1. **API-Driven & Config-Driven (No CSV Uploads)**
   - Pulls contract rates directly from Zipaworld REST endpoints via a secure backend HTTP client (`httpx`).
   - Supports custom header auth or Bearer token authorization.
   - Configurable pagination styles: `none`, `page`, `offset`, and `cursor`.
   - Dynamic response parsing with `config/field-map.json` mapping arbitrary API structures to canonical schema.
   - Zero CSV upload routes anywhere in the system; export-only functionality with spreadsheet formula injection protection.

2. **Accurate Date-Only Expiry Mathematics**
   - Configurable business timezone (default: `Asia/Kolkata`).
   - Inclusive end dates: contracts ending today remain valid and are flagged as `"Expires today"`.
   - Real-time status evaluation at request time:
     - `ACTIVE`: Valid contract beyond warning window.
     - `EXPIRING SOON`: Valid contract within threshold (default 14 days, adjustable 1–90 days).
     - `EXPIRED`: Validity end date elapsed.
     - `STARTS LATER`: Future-effective contract.
     - `NEEDS REVIEW`: Missing, malformed, or inverted validity dates.

3. **Carrier-Depth Coverage Analytics**
   - Evaluates multi-carrier redundancy against target minimum thresholds (default: 2 carriers).
   - Classifications: `COVERED`, `THIN COVER`, `ALL EXPIRED`, and `GAP (no rate)`.
   - Distinct carrier brand canonicalization (e.g., MSC Agency, Sealand/Hamburg Süd to Maersk, Hapag-Lloyd, CMA CGM).
   - Dedicated monitoring hubs for:
     - **Watched Destination Countries** (with search-autocomplete additions and completeness disclaimer).
     - **Watched Gateway Ports** (with 5-character UN/LOCODE validation).
     - **India Port-Region Operational Board** (West, South, East, North ICDs, Central, and Unclassified ports with interactive classification persistence).

4. **Honest Synchronization & Snapshot Diffs**
   - Clear connection chips: `DEMO`, `LIVE`, `STALE`, `NOT CONFIGURED`, or `NO DATA`.
   - Preserves previous valid dataset upon upstream connection errors or empty feeds.
   - Automated delta tracking between sync cycles recording added, updated, and removed rates with field-level mutations.
   - Transparent disclaimer: Snapshot diffs are dashboard-stored delta logs, not Zipaworld audit history.

5. **Operational Action Center & Master Repository**
   - Filterable data table with server-side pagination, search, corridor direction detection, and multi-parameter sorting.
   - Three-tier rate inspection drawer:
     1. Source Data (raw values directly from Zipaworld).
     2. Calculated by Rate Radar (enrichment, canonical brands, days remaining).
     3. Contextual Suggested Actions for freight desks.

---

## Technology Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn.
- **Client**: `httpx` (read-only GET requests, exponential backoff, Retry-After handling for HTTP 429).
- **Storage**: SQLite3 via Python standard library with atomic transactions.
- **Scheduler**: APScheduler with `asyncio.Lock` preventing concurrent runs.
- **Validation & Settings**: Pydantic v2 & `pydantic-settings`.
- **Frontend**: Vanilla HTML5, Custom CSS3 Design System (Dark mode, logistics aesthetics, radar sweep animation), Vanilla ES6 JavaScript.

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.11 or higher
- `pip` package manager

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone <repo-url>
cd Rate_Tracker
pip install -r requirements.txt
```

### 2. Running in Demo Mode (Synthetic Data)
To evaluate the application without live Zipaworld API credentials:
```bash
# Windows PowerShell
$env:RADAR_MODE="demo"
python -m uvicorn app.main:app --host 127.0.0.1 --port 3000

# macOS / Linux
export RADAR_MODE="demo"
python -m uvicorn app.main:app --host 127.0.0.1 --port 3000
```
Open your browser and navigate to:
```
http://127.0.0.1:3000
```
The application will start, seed 60+ synthetic records showcasing all statuses, and display a prominent `DEMO` badge.

### 3. Running in Live Production Mode
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Populate the Zipaworld API parameters in `.env`:
   ```ini
   RADAR_MODE=live
   ZIPAWORLD_BASE_URL=https://api.zipaworld.com/v1
   ZIPAWORLD_RATES_PATH=/rates
   ZIPAWORLD_AUTH_MODE=header
   ZIPAWORLD_AUTH_HEADER_NAME=x-api-key
   ZIPAWORLD_API_KEY=your_actual_key_here
   ZIPAWORLD_ITEMS_PATH=data.rates
   ZIPAWORLD_PAGINATION_STYLE=page
   ZIPAWORLD_PAGE_PARAM=page
   ZIPAWORLD_PAGE_SIZE_PARAM=limit
   ZIPAWORLD_PAGE_SIZE=100
   ```
3. Run the server:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 3000
   ```

---

## Testing & Quality Assurance

The codebase includes an extensive automated test suite covering expiry mathematics, normalization rules, carrier mapping, sync error resilience, and route security:

```bash
# Run complete test suite
python -m pytest -v
```

All 113 automated unit and integration tests pass:
- Expiry rule boundaries (inclusive today, yesterday expired, threshold changes)
- Deduplication and derived key generation
- Carrier legal name canonicalization
- Trade direction evaluation (rateType priority over UN/LOCODE countries)
- Snapshot diff generation and stale data retention
- Absence of CSV upload endpoints and formula injection prevention

---

## Configuration Reference (`config/field-map.json`)

The field mapping file translates arbitrary API JSON response paths into Rate Radar's internal schema:

| Canonical Field | Type | Description |
|---|---|---|
| `rate_id` | string | Unique rate ID (derived key generated if missing) |
| `origin_raw` | string | Unparsed origin location string (e.g. `INMUN, Mundra (India)`) |
| `destination_raw` | string | Unparsed destination location string |
| `shipment_mode` | string | Mode (`FCL` or `LCL`) |
| `container_name` | string | Equipment type (`20 Standard`, `40 High Cube`, etc.) |
| `carrier_raw` | string | Legal carrier name |
| `rate` | float | Monetary tariff value |
| `currency` | string | ISO currency code (`USD`, `INR`, `EUR`) |
| `validity_start_date`| string | ISO or DD/MM/YYYY start date |
| `validity_end_date` | string | ISO or DD/MM/YYYY expiration date |
| `rate_type` | string | Operational rate code (`OE`, `OI`, `AE`, `AI`, etc.) |

---

## Security & Operational Guardrails

- **Read-Only API Integration**: The backend issues strictly `GET` requests to Zipaworld and never creates, updates, or deletes records externally.
- **Credential Protection**: API keys and tokens are restricted to backend environment variables. They never appear in logs, error payloads, or client bundles.
- **Rate-Limiting**: Manual sync triggers are throttled to once every 30 seconds to prevent denial-of-service on upstream endpoints.
- **HTTP 429 & Retry-After**: The HTTP client automatically honors `Retry-After` headers and applies exponential backoff with jitter.
- **Fail-Safe Persistence**: Empty API responses or connection dropouts do not purge the existing database; the system retains the last known good dataset and flags it as `STALE`.

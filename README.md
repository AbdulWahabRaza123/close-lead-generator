# Close CRM CSV Import & State Report

Import companies and contacts from CSV into [Close CRM](https://close.com/) via the Close API, then generate a **state-level revenue report** for leads founded within a date range.

Built for the Close Software Engineer Support take-home; structured for local CLI use today and **multi-tenant API deployment** as a next step.

---

## Table of contents

1. [What this project does](#what-this-project-does)
2. [System requirements](#system-requirements)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [How to run](#how-to-run)
6. [Outputs](#outputs)
7. [Input CSV format](#input-csv-format)
8. [Project structure](#project-structure)
9. [Troubleshooting](#troubleshooting)
10. [Testing](#testing)
11. [Future: Multi-user API service](#future-multi-user-api-service)
12. [Submission (Part 2)](#submission-part-2)

---

## What this project does

| Step | Action |
|------|--------|
| 1 | Read CSV (one row = one contact) |
| 2 | Discard invalid rows (logged to file) |
| 3 | Group contacts by **company** → one Close **lead** per company |
| 4 | Import leads + contacts via Close API |
| 5 | Search Close for leads founded between `--start-date` and `--end-date` |
| 6 | Filter to this import batch (optional but default) |
| 7 | Build report by US state → `output/report.csv` |
| 8 | Reconcile CSV logic vs API results |

**Invalid rows are discarded when:** company name is missing, or there is no valid email and no valid phone.

**Report includes a company when:** founded date in range, state present, revenue present.

---

## System requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10+, macOS, or Linux |
| **Python** | **3.9+** required (see [Python version](#python-version) below) |
| **pip** | Bundled with Python |
| **Internet** | Required for Close API |
| **Close account** | [14-day trial](https://app.close.com/signup) or paid org |
| **Close API key** | [Create here](https://help.close.com/docs/api-keys) |
| **Disk space** | ~50 MB (including virtual environment) |
| **RAM** | 512 MB+ for typical CSV sizes |

No database, Docker, or Node.js required for the CLI version.

### Python version

| Version | Supported |
|---------|-----------|
| **3.9** | Minimum (required) |
| **3.10 – 3.12** | Recommended |
| **3.11** | Used for development and testing |
| **3.8 and older** | Not supported |

Check what you have installed:

**Windows:**

```powershell
python --version
# or, if you use the Python launcher:
py --version
py -3.11 --version
```

**macOS / Linux:**

```bash
python3 --version
```

You should see something like `Python 3.11.x` or `Python 3.10.x`. If the version is below 3.9, install a newer Python from [python.org](https://www.python.org/downloads/) before continuing.

---

## Installation

### 1. Clone or download the project

```bash
cd path/to/file-processing
```

### 2. Create a virtual environment (Python 3.9+)

A virtual environment keeps dependencies isolated from other Python projects on your machine. Use the same Python 3.9+ interpreter you verified above.

**Windows (PowerShell):**

```powershell
python -m venv venv
# If you have multiple Python versions installed:
# py -3.11 -m venv venv

.\venv\Scripts\Activate.ps1
```

If activation is blocked by execution policy:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv venv
# Or pin a specific version, e.g.:
# python3.11 -m venv venv

source venv/bin/activate
```

When the venv is active, your prompt usually shows `(venv)`.

Confirm the venv is using the correct Python:

```bash
python --version
```

Expected: `Python 3.9.x` or higher.

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Dependencies installed:**

| Package | Purpose |
|---------|---------|
| `requests` | Close REST API HTTP calls |
| `pandas` | CSV handling and report tables |
| `python-dotenv` | Load `CLOSE_API_KEY` from `.env` |

### 4. Verify installation

```bash
python -c "import requests, pandas, dotenv; print('OK')"
python tests/validate_requirements.py
```

---

## Configuration

### 1. Create environment file

**Windows:**

```powershell
copy .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

### 2. Add your Close API key

Edit `.env`:

```env
CLOSE_API_KEY=api_your_key_here
DRY_RUN=false
```

Never commit `.env` to Git (it is listed in `.gitignore`).

### 3. Optional: Close custom fields (recommended for production)

In Close → **Settings → Custom Fields → Lead**, create:

| Field | Type |
|-------|------|
| Company Founded | Date |
| Company Revenue | Number |

Add IDs to `.env`:

```env
CLOSE_CF_FOUNDED_DATE=cf_xxxxxxxx
CLOSE_CF_REVENUE=cf_yyyyyyyy
```

If omitted, founded date and revenue are stored in the lead **description** and filtered by the script.

---

## How to run

Run these commands **with the virtual environment activated** and **Python 3.9+** (`python --version`).

### Basic command (required arguments)

```bash
python main.py \
  --csv "Customer Support Engineer Take Home Project - Import File - MOCK_DATA.csv" \
  --start-date 1965-01-01 \
  --end-date 2019-12-31
```

**Windows (single line):**

```powershell
python main.py --csv "Customer Support Engineer Take Home Project - Import File - MOCK_DATA.csv" --start-date 1965-01-01 --end-date 2019-12-31
```

**macOS / Linux (single line):**

```bash
python3 main.py --csv "Customer Support Engineer Take Home Project - Import File - MOCK_DATA.csv" --start-date 1965-01-01 --end-date 2019-12-31
```

### Suggested date range for MOCK_DATA

The sample file contains founded dates from roughly **1963–2022**. For most companies in range:

```text
--start-date 1965-01-01 --end-date 2019-12-31
```

### CLI flags

| Flag | Required | Description |
|------|----------|-------------|
| `--csv` | Yes | Path to input CSV |
| `--start-date` | Yes | Founded range start (`YYYY-MM-DD`) |
| `--end-date` | Yes | Founded range end (`YYYY-MM-DD`) |
| `--batch-id` | No | Custom import batch tag (auto-generated if omitted) |
| `--skip-import` | No | Skip import; report only (uses saved manifest) |
| `--all-org-leads` | No | Include all org leads in range, not only this import |
| `--no-reconcile` | No | Skip CSV vs API reconciliation |
| `--report-from-csv` | No | Dev only: build report from CSV, not Close API |
| `--verbose` | No | Debug logging |

### Dry run (no writes to Close)

Set in `.env`:

```env
DRY_RUN=true
```

Then run the same command. API calls are simulated in memory.

---

## Outputs

| File | Description |
|------|-------------|
| `output/report.csv` | State-level report (final deliverable) |
| `output/reconciliation.csv` | Per-state CSV vs API comparison |
| `output/import_manifest.json` | Companies imported in this run + batch ID |
| `logs/invalid_rows.log` | Discarded rows with reasons |

**Report columns** (match sample output format):

- `US State`
- `Total number of leads`
- `The lead with most revenue`
- `Total revenue`
- `Median revenue`

**Success indicator in console:**

```text
Reconciliation: PASS — CSV and Close API reports match per state.
```

---

## Input CSV format

| Column | Required | Notes |
|--------|----------|-------|
| `Company` | Yes | Becomes Close lead name |
| `Contact Name` | No | Defaults from email if empty |
| `Contact Emails` | No* | *Need email **or** phone |
| `Contact Phones` | No* | International formats supported |
| `custom.Company Founded` | No | `DD.MM.YYYY` or `D.M.YYYY` |
| `custom.Company Revenue` | No | e.g. `$1,234,567.89` |
| `Company US State` | No | Full name, e.g. `California` |

---

## Project structure

```text
file-processing/
├── main.py                 # CLI entry point
├── close_api.py            # Close REST client
├── validators.py           # Row validation
├── parsers.py              # Dates, currency, email, phone
├── report_generator.py     # State report + metrics
├── csv_loader.py           # Multiline-safe CSV read
├── import_manifest.py      # Per-run company list
├── lead_filter.py          # Filter API results to import batch
├── state_utils.py          # State name normalization
├── config.py               # Paths and env settings
├── requirements.txt
├── .env.example
├── output/                 # Generated reports
├── logs/                   # Invalid row log
├── tests/                  # Integration tests
└── scripts/
    └── reconcile.py        # Standalone reconciliation
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Python 3.9+ required` / syntax errors on old Python | Upgrade to Python 3.9+ and recreate venv: `python -m venv venv` |
| `python` not found (Windows) | Install from [python.org](https://www.python.org/downloads/) and check **Add Python to PATH**, or use `py -3.11` |
| `CLOSE_API_KEY is not set` | Create `.env` from `.env.example` and add your key |
| `CSV missing required columns` | Use the official MOCK_DATA headers |
| `ExecutionPolicy` on Windows | Run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `pip` not found | Use `python -m pip install -r requirements.txt` |
| Report counts look wrong | Delete test leads in Close or use a fresh org; re-run import once |
| Reconciliation FAIL | Run with default import filter (omit `--all-org-leads`) |
| Rate limits from Close | Wait and retry; add backoff (see future API section) |

---

## Testing

```bash
# Static checks
python tests/validate_requirements.py

# Live API tests (requires CLOSE_API_KEY in .env)
python tests/run_integration_tests.py
```

---

## Future: Multi-user API service

Today the tool is a **CLI** that reads CSV from disk and writes reports to `output/`. The next step is a **hosted API** so many users can upload CSV in one request and receive a report without using local files.

### Goals

| Today (CLI) | Future (API) |
|-------------|----------------|
| CSV path on disk | CSV in HTTP request body (multipart or base64) |
| `output/report.csv` on disk | Return file in response **or** upload to object storage |
| Single Close org per `.env` | Per-tenant Close API key (or OAuth) |
| `import_manifest.json` on disk | Job record in DB / Redis |

### High-level architecture

```text
                    ┌─────────────────┐
  Client (UI/app)   │   API Gateway   │
        │           │  (FastAPI etc.) │
        └──────────►└────────┬────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Job queue         │
                    │   (Celery / RQ)     │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ Worker       │    │ PostgreSQL   │    │ Object store │
  │ (reuse       │    │ jobs, users, │    │ R2 / S3 /    │
  │  main.py     │    │ manifests    │    │ GCS          │
  │  logic)      │    └──────────────┘    └──────────────┘
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ Close API    │
  │ (per user)   │
  └──────────────┘
```

### Proposed API endpoints

#### Option A — Synchronous (small files only)

```http
POST /v1/jobs/import-report
Content-Type: multipart/form-data

Fields:
  file: <csv>
  start_date: 1965-01-01
  end_date: 2019-12-31
  close_api_key: <user's key>   # or Authorization header

Response 200:
  Content-Type: text/csv
  Body: report.csv bytes

  OR

Response 200:
  {
    "job_id": "job_abc123",
    "report_url": "https://cdn.example.com/reports/job_abc123/report.csv",
    "reconciliation": { "status": "PASS", "states": [...] },
    "invalid_rows_url": "https://..."
  }
```

#### Option B — Asynchronous (recommended for production)

```http
POST /v1/jobs
→ 202 Accepted { "job_id": "job_abc123", "status": "queued" }

GET /v1/jobs/job_abc123
→ 200 { "status": "completed", "report_url": "...", "reconciliation": "PASS" }
```

### Input: no disk required

```python
# Pseudocode — worker receives bytes, not a file path
def process_job(csv_bytes: bytes, start_date: str, end_date: str, close_api_key: str):
    df = load_csv_from_bytes(csv_bytes)          # csv_loader extension
    valid_rows = validate_dataframe(df)
    groups = group_by_company(valid_rows)
    client = CloseAPIClient(api_key=close_api_key)
    batch_id = generate_batch_id()
    import_companies(client, groups, batch_id)
    leads = client.search_leads(start_date, end_date)
    leads = filter_leads_for_import(leads, manifest_companies=set(groups), batch_id=batch_id)
    report_df = build_state_report(leads)
    return report_df, invalid_rows_log
```

Refactor: add `load_csv_from_bytes()` next to `load_csv_as_dataframe()`.

### Output: three delivery options

| Option | Pros | Cons |
|--------|------|------|
| **1. Direct HTTP response** | Simplest; no extra infra | Size limits; timeouts on large imports |
| **2. Presigned URL (S3 / R2 / GCS)** | Scalable; client downloads when ready | Needs bucket + credentials |
| **3. Webhook callback** | Good for integrations | Client must host endpoint |

#### Example: Cloudflare R2 (S3-compatible)

```python
import boto3

def upload_report_to_r2(report_path: Path, job_id: str) -> str:
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )
    key = f"reports/{job_id}/report.csv"
    s3.upload_file(str(report_path), os.environ["R2_BUCKET"], key)
    return f"{os.environ['R2_PUBLIC_BASE_URL']}/{key}"
```

Same pattern works for **AWS S3** and **Google Cloud Storage** (different endpoint and credentials).

#### Example: return file directly (FastAPI)

```python
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse
import io

@app.post("/v1/jobs/import-report")
async def import_report(
    file: UploadFile = File(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
):
    csv_bytes = await file.read()
    report_df, _ = process_job(csv_bytes, start_date, end_date, get_user_close_key())
    buffer = io.StringIO()
    report_df.to_csv(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )
```

### Multi-tenancy and security

| Concern | Approach |
|---------|----------|
| **Close API key per user** | Store encrypted in DB; never log; pass to worker only in memory |
| **Isolate imports** | Batch ID per job: `batch=user_{id}_job_{job_id}` |
| **Rate limits** | Queue workers; exponential backoff on Close 429 |
| **File size** | Max upload 10–50 MB; async job over threshold |
| **Auth** | API keys, JWT, or session for your API (separate from Close key) |

### Suggested implementation phases

| Phase | Deliverable |
|-------|-------------|
| **1** | Extract core logic into `pipeline.py` callable from CLI and workers |
| **2** | FastAPI `POST /v1/jobs` + in-memory CSV (no disk) |
| **3** | Redis/Celery queue for long-running imports |
| **4** | R2/S3 upload + presigned download URLs |
| **5** | Per-user Close keys + job history UI |

### New dependencies (future API service)

```text
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9    # file uploads
boto3>=1.34.0              # S3 / R2
celery>=5.3.0              # optional queue
redis>=5.0.0               # optional broker
```

Keep the CLI (`main.py`) as-is; the API layer calls the same functions.

---

## Submission (Part 2)

1. Push to a **private** GitHub repository.
2. Record a **5–10 minute Loom** — see [LOOM_OUTLINE.md](LOOM_OUTLINE.md).
3. Email **katie.kemp@close.com** and **joseph@close.com** with repo access and Loom link.

See [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md) for spec mapping.

---

## License

Assessment / educational use.

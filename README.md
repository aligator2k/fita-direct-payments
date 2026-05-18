# Fita Direct Payments

Pipeline that connects to a MySQL database, asks Google Gemini for SQL queries and insights, runs them, and produces an HTML report.

## Run with Docker (recommended)

Prerequisites: Docker Desktop installed and running.

1. Copy `.env.example` to `.env` and fill in your values.
2. Build and run:

```bash
docker compose up --build
```

The container builds, runs the pipeline, and exits. Output files appear in `./output/`. Open `output/report.html` in a browser.

## Run locally with Python

Prerequisites: Python 3.12 or later.

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # then edit .env
python main.py
```

## Configuration

All settings live in `.env`. Required keys:

GEMINI_API_KEY=your_key_here
DB_HOST=...
DB_PORT=3306
DB_USER=...
DB_PASSWORD=...
DB_NAME=…

Get a free Gemini API key at https://aistudio.google.com/app/apikey

## What it does

1. `schema_extractor.py` connects to MySQL, reads `information_schema`, builds a structured text description
2. `plan_generator.py` sends the schema to Gemini, gets back a JSON plan of 6-8 visualizations
3. `report_builder.py` for each plan item: asks Gemini for SQL, runs it, renders a matplotlib chart, asks Gemini for insights, combines everything into one HTML file
4. `main.py` orchestrates all three with logging

Outputs land in `./output/`:
- `report.html` — final report
- `pipeline.log` — full run log
- `plan.json` — the plan Gemini produced
- `schema_description.txt` — extracted schema
- `aggregated_data.json`, `plan_raw.txt` — intermediates

## Models used

The Gemini client (`gemini_client.py`) tries multiple models in order, falling back to the next when one hits the free-tier rate limit:

- gemini-2.5-flash
- gemini-2.0-flash
- gemini-2.5-flash-lite
- gemini-flash-latest

Module-level state remembers which one worked last so subsequent calls skip ahead.
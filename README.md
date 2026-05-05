# fita-direct-payments

MySQL + Gemini schema analysis



\# Fita Direct Payments



Python project that connects to a MySQL database, sends its schema to Google Gemini, and uses the LLM to generate SQL queries and written insights.



\## Overview



Three scripts, run in order:



1\. `schema\_extractor.py` connects to MySQL, pulls table and column metadata from `information\_schema`, builds a structured text description, and saves it to `output/schema\_description.txt`.

2\. `query\_generator.py` sends that schema to Gemini, asks for 5 aggregated KPI queries as JSON, runs each query against MySQL, and saves the results to `output/aggregated\_data.json`.

3\. `insights\_generator.py` sends the schema plus aggregated data back to Gemini, asks for a written analysis, and saves it to `output/insights\_report.md`.



\## Setup



```bash

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

pip install -r requirements.txt

```



Create a `.env` file in the project root with the following keys:

GEMINI\_API\_KEY=your\_key\_here

DB\_HOST=...

DB\_PORT=3306

DB\_USER=...

DB\_PASSWORD=...

DB\_NAME=...



Get a free Gemini API key at https://aistudio.google.com/app/apikey



\## Run



```bash

python schema\_extractor.py

python query\_generator.py

python insights\_generator.py

```



Outputs land in the `output/` folder.


"""
Sends the schema description to Gemini, asks for SQL queries that compute
aggregated KPIs, runs the SQL against the MySQL server, and saves the
aggregated data to a JSON file.
"""

import os
import json
import re
from dotenv import load_dotenv
import mysql.connector
import google.generativeai as genai

from schema_extractor import build_schema_description

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


PROMPT_TEMPLATE = """You are a SQL and data analysis expert.

Below is the schema of a MySQL database. There are no foreign keys declared,
but logical relationships are listed at the bottom.

{schema}

Suggest 5 SQL queries that compute the most useful aggregated KPIs for this
data. Each query must:
- Be a single valid MySQL SELECT statement
- Use only the tables and columns shown above
- Return aggregated data (no raw row dumps)
- Be safe to run as-is, no INSERT, UPDATE, DELETE, or DDL

Return your answer as a JSON array. Each item must be an object with these keys:
  "name": short snake_case identifier for the KPI
  "description": one sentence explaining what the query measures
  "sql": the SQL query as a single string

Return ONLY the JSON array. No prose, no markdown fences, no explanations.
"""


def ask_gemini_for_queries(schema_text):
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = PROMPT_TEMPLATE.format(schema=schema_text)
    response = model.generate_content(prompt)
    return response.text


def extract_json(raw_text):
    """Strip markdown fences if Gemini added them, then parse JSON."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def get_data_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def run_query(sql):
    conn = get_data_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def to_jsonable(rows):
    """Convert datetime, Decimal etc. to plain types so json.dump works."""
    out = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif isinstance(v, (int, float, str, bool)) or v is None:
                clean[k] = v
            else:
                clean[k] = str(v)
        out.append(clean)
    return out


def main():
    schema_text = build_schema_description(os.getenv("DB_NAME"))
    print("Asking Gemini for SQL queries...")
    raw = ask_gemini_for_queries(schema_text)

    raw_path = os.path.join("output", "gemini_queries_raw.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"Raw Gemini response saved to {raw_path}")

    queries = extract_json(raw)
    print(f"Got {len(queries)} queries.\n")

    results = []
    for q in queries:
        name = q.get("name", "unnamed")
        sql = q.get("sql", "").strip().rstrip(";")
        description = q.get("description", "")
        print(f"Running: {name}")
        try:
            rows = run_query(sql)
            results.append({
                "name": name,
                "description": description,
                "sql": sql,
                "rows": to_jsonable(rows),
            })
            print(f"  -> {len(rows)} rows")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "name": name,
                "description": description,
                "sql": sql,
                "error": str(e),
            })

    out_path = os.path.join("output", "aggregated_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAggregated data saved to {out_path}")


if __name__ == "__main__":
    main()
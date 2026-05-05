"""
Reads the aggregated data and the schema description, sends both back to
Gemini, and asks for written insights and descriptions of the dataset.
"""

import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


PROMPT_TEMPLATE = """You are a data analyst writing a short report for a
business stakeholder.

Below is the schema of a database followed by aggregated KPI data computed
from that database. Use both to write a clear, factual analysis.

=== SCHEMA ===
{schema}

=== AGGREGATED DATA ===
{data}

Write a report with these sections:

1. Dataset overview (2 to 3 sentences describing what this database represents)
2. Key findings (5 to 7 bullet points, each grounded in a specific number from the data above)
3. Notable patterns or anomalies (anything unusual in trends, distributions or gaps)
4. Suggested next steps for further analysis (3 to 4 ideas)

Rules:
- Use plain language, no jargon
- Cite specific numbers from the aggregated data when making claims
- Do not invent metrics that are not in the data
- Keep the whole report under 500 words
"""


def main():
    schema_path = os.path.join("output", "schema_description.txt")
    data_path = os.path.join("output", "aggregated_data.json")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_text = f.read()

    with open(data_path, "r", encoding="utf-8") as f:
        aggregated = json.load(f)

    data_text = json.dumps(aggregated, indent=2, ensure_ascii=False)

    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = PROMPT_TEMPLATE.format(schema=schema_text, data=data_text)

    print("Asking Gemini for insights...")
    response = model.generate_content(prompt)
    report = response.text

    out_path = os.path.join("output", "insights_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport saved to {out_path}\n")
    print("=" * 60)
    print(report)


if __name__ == "__main__":
    main()
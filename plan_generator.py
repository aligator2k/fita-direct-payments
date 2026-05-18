"""
Asks Gemini to produce a visualization plan for the direct_payments database.
The plan is a JSON list. Each item describes one aggregation, its visual type,
and a short caption. Saved to output/plan.json so it can be consumed by
report_builder.py.
"""

import os
import json
import re
from dotenv import load_dotenv
load_dotenv()
from gemini_client import ask_gemini
from schema_extractor import build_schema_description


PROMPT_TEMPLATE = """You are a data analytics expert. Below is the schema of
a MySQL database called direct_payments. There are no foreign keys declared,
but there are clear logical relationships listed at the bottom.

{schema}

Produce a visualization plan for a one-page report aimed at a business
stakeholder. The plan must contain 6 to 8 items.

Each item must be a JSON object with these keys:
  "id": short snake_case identifier, unique
  "title": human-readable title shown above the chart
  "description": one sentence explaining what the chart shows
  "aggregation": plain-language description of the data aggregation
                 (e.g. "monthly total payment amount based on charge_date",
                 "top 10 organisations by total payment amount")
  "visual_type": one of: "line", "bar_horizontal", "bar_vertical",
                 "stacked_bar", "donut", "kpi", "table"
  "x_field": logical name for the x-axis or category field (or null for kpi)
  "y_field": logical name for the y-axis or value field (or null for kpi)

Cover a mix of:
- High-level KPIs (totals, counts, averages) using visual_type "kpi"
- Time-based trends (visual_type "line") using charge_date
- Category breakdowns (bar charts or donut) by parent_vertical, scheme, or source
- At least one ranking (top N) chart

Return ONLY a JSON array of items. No markdown fences, no prose, no comments.
"""


def ask_gemini_for_plan(schema_text):
    prompt = PROMPT_TEMPLATE.format(schema=schema_text)
    return ask_gemini(prompt)


def extract_json(raw_text):
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def main():
    schema_text = build_schema_description(os.getenv("DB_NAME"))

    print("Asking Gemini for the visualization plan...")
    raw = ask_gemini_for_plan(schema_text)

    raw_path = os.path.join("output", "plan_raw.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"Raw response saved to {raw_path}")

    plan = extract_json(raw)
    print(f"Got {len(plan)} plan items.\n")

    for item in plan:
        print(f"- [{item.get('visual_type', '?')}] {item.get('title', '')}")

    plan_path = os.path.join("output", "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"\nPlan saved to {plan_path}")


if __name__ == "__main__":
    main()
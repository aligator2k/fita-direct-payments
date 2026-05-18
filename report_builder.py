"""
Builds a complete HTML report from a plan in output/plan.json.

For each plan item:
  - Asks Gemini for a single SQL query that produces the data needed
  - Runs the SQL against MySQL
  - Renders a matplotlib chart based on the visual_type in the plan
  - Asks Gemini for a short written description with concrete insights
  - Embeds the chart and the text into a single HTML page

Saves output/report.html
"""

import os
import io
import json
import re
import base64
from jinja2 import Template
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
import mysql.connector
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from gemini_client import ask_gemini
from schema_extractor import build_schema_description

# ---------- DB helpers ----------

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def run_query(sql):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def is_safe_select(sql):
    """Block anything that isn't a single SELECT statement."""
    s = sql.strip().rstrip(";").strip().lower()
    if not s.startswith(("select", "with")):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "create",
                 "truncate", "grant", "revoke", "rename", "replace"]
    for word in forbidden:
        if re.search(r"\b" + word + r"\b", s):
            return False
    if ";" in s:
        return False
    return True


# ---------- Gemini helpers ----------

def strip_fences(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|sql)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned


SQL_PROMPT = """You are a SQL expert. Below is the schema of a MySQL database
called direct_payments and a single visualization plan item. Write a single
MySQL SELECT query that returns the data needed for the chart.

=== SCHEMA ===
{schema}

=== PLAN ITEM ===
{item}

Rules:
- Return ONLY the SQL, no markdown fences, no commentary
- Single SELECT statement, no INSERT/UPDATE/DELETE/DDL
- Use only tables and columns shown in the schema
- For "kpi" items, return a single row with the metric value
- For "line" items, return ordered rows with one date column and one value column
- For "donut", "bar_*", "stacked_bar", "table": return aggregated rows ready to plot
- For "stacked_bar" return one row per (category, group, value) combination
- For ranking ("Top N") items, include LIMIT
- Column names should be sensible and lowercase, no spaces (use underscores)
"""


INSIGHT_PROMPT = """You are a data analyst. Below is a plan item for a chart
and the actual aggregated data the SQL query produced. Write a short caption
and one or two concrete insights about the data.

=== PLAN ITEM ===
{item}

=== DATA (JSON) ===
{data}

Rules:
- 2 to 4 sentences total
- Cite specific numbers from the data
- Plain prose, no bullet points
- Do not invent metrics that are not in the data
- Return only the prose, no headings, no markdown
"""


def gemini_call(prompt):
    return ask_gemini(prompt)

def ask_for_sql(schema_text, item):
    prompt = SQL_PROMPT.format(schema=schema_text, item=json.dumps(item, indent=2))
    return strip_fences(gemini_call(prompt))


def ask_for_insight(item, rows):
    safe_rows = []
    for r in rows[:50]:
        clean = {}
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif isinstance(v, (int, float, str, bool)) or v is None:
                clean[k] = v
            else:
                clean[k] = str(v)
        safe_rows.append(clean)
    prompt = INSIGHT_PROMPT.format(
        item=json.dumps(item, indent=2),
        data=json.dumps(safe_rows, indent=2, ensure_ascii=False),
    )
    return gemini_call(prompt).strip()


# ---------- Chart rendering ----------

def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def render_chart(item, rows):
    """Render based on visual_type. Returns base64 PNG, or None for KPI."""
    visual_type = item.get("visual_type", "")
    if not rows:
        return None

    if visual_type == "kpi":
        return None  # KPIs render as text in the HTML, not as an image

    columns = list(rows[0].keys())

    if visual_type == "line":
        x_col, y_col = columns[0], columns[1]
        xs = [r[x_col] for r in rows]
        ys = [float(r[y_col]) if r[y_col] is not None else 0 for r in rows]

        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(xs, ys, marker="o", linewidth=2, color="#4C9AFF")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        plt.xticks(rotation=45, ha="right")
        ax.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()
        return fig_to_base64(fig)

    if visual_type in ("bar_vertical", "bar_horizontal"):
        x_col, y_col = columns[0], columns[1]
        labels = [str(r[x_col]) for r in rows]
        values = [float(r[y_col]) if r[y_col] is not None else 0 for r in rows]

        fig, ax = plt.subplots(figsize=(10, 5))
        if visual_type == "bar_horizontal":
            ax.barh(labels, values, color="#4C9AFF")
            ax.invert_yaxis()
            ax.set_xlabel(y_col)
            ax.set_ylabel(x_col)
        else:
            ax.bar(labels, values, color="#4C9AFF")
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            plt.xticks(rotation=30, ha="right")
        ax.grid(True, axis="x" if visual_type == "bar_horizontal" else "y", alpha=0.3)
        plt.tight_layout()
        return fig_to_base64(fig)

    if visual_type == "donut":
        x_col, y_col = columns[0], columns[1]
        labels = [str(r[x_col]) for r in rows]
        values = [float(r[y_col]) if r[y_col] is not None else 0 for r in rows]

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.pie(values, labels=labels, autopct="%1.1f%%",
               wedgeprops=dict(width=0.4), startangle=90)
        ax.set_aspect("equal")
        plt.tight_layout()
        return fig_to_base64(fig)

    if visual_type == "stacked_bar":
        # Expect columns: x_category, group, value
        x_col, group_col, val_col = columns[0], columns[1], columns[2]
        # Build pivot manually
        x_values = []
        groups = []
        for r in rows:
            if r[x_col] not in x_values:
                x_values.append(r[x_col])
            if r[group_col] not in groups:
                groups.append(r[group_col])

        data = {g: [0] * len(x_values) for g in groups}
        for r in rows:
            xi = x_values.index(r[x_col])
            data[r[group_col]][xi] = float(r[val_col]) if r[val_col] is not None else 0

        fig, ax = plt.subplots(figsize=(10, 5))
        bottom = [0] * len(x_values)
        colors = ["#4C9AFF", "#FF6B35", "#7FBA00", "#A463F2", "#FFB800"]
        for i, g in enumerate(groups):
            ax.bar([str(x) for x in x_values], data[g], bottom=bottom,
                   label=str(g), color=colors[i % len(colors)])
            bottom = [bottom[j] + data[g][j] for j in range(len(x_values))]
        ax.set_xlabel(x_col)
        ax.set_ylabel(val_col)
        ax.legend()
        plt.xticks(rotation=30, ha="right")
        ax.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()
        return fig_to_base64(fig)

    if visual_type == "table":
        return None  # Table rendered as HTML directly

    return None


# ---------- HTML template ----------

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Direct Payments Report</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { border-bottom: 2px solid #4C9AFF; padding-bottom: 0.4rem; }
  .meta { color: #777; font-size: 0.9rem; margin-bottom: 2rem; }
  .item { border: 1px solid #e5e5e5; border-radius: 8px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem; background: #fafafa; }
  .item h2 { margin-top: 0; color: #2c5282; }
  .item .description { color: #555; font-style: italic; margin-bottom: 0.8rem; }
  .item .insight { background: white; padding: 0.8rem; border-left: 3px solid #4C9AFF; border-radius: 4px; margin-top: 1rem; }
  .kpi-value { font-size: 2.2rem; font-weight: bold; color: #2c5282; margin: 0.5rem 0; }
  img { max-width: 100%; height: auto; display: block; margin: 1rem 0; }
  table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
  th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
  th { background: #f0f4f8; }
  details { margin-top: 0.8rem; }
  summary { cursor: pointer; color: #888; font-size: 0.85rem; }
  pre { background: #f4f4f4; padding: 0.6rem; border-radius: 4px; overflow-x: auto; font-size: 0.8rem; }
</style>
</head>
<body>

<h1>Direct Payments Report</h1>
<div class="meta">Generated {{ generated_at }} from database <code>{{ db_name }}</code>. {{ items|length }} sections.</div>

{% for item in items %}
<div class="item">
  <h2>{{ item.title }}</h2>
  <div class="description">{{ item.description }}</div>

  {% if item.error %}
    <p style="color: red;"><strong>Error:</strong> {{ item.error }}</p>
  {% elif item.visual_type == "kpi" and item.kpi_value is not none %}
    <div class="kpi-value">{{ item.kpi_value }}</div>
  {% elif item.visual_type == "table" and item.rows %}
    <table>
      <thead><tr>{% for col in item.columns %}<th>{{ col }}</th>{% endfor %}</tr></thead>
      <tbody>
        {% for r in item.rows %}<tr>{% for col in item.columns %}<td>{{ r[col] }}</td>{% endfor %}</tr>{% endfor %}
      </tbody>
    </table>
  {% elif item.chart_b64 %}
    <img src="data:image/png;base64,{{ item.chart_b64 }}" alt="{{ item.title }}">
  {% endif %}

  {% if item.insight %}<div class="insight">{{ item.insight }}</div>{% endif %}

  <details>
    <summary>Show SQL and raw data</summary>
    <pre>{{ item.sql }}</pre>
    <pre>{{ item.raw_data }}</pre>
  </details>
</div>
{% endfor %}

</body>
</html>
"""


# ---------- Main pipeline ----------

def format_kpi_value(rows):
    """Try to format a single-row, single-column KPI result into a string."""
    if not rows:
        return None
    row = rows[0]
    if not row:
        return None
    # Take the first numeric value found
    for k, v in row.items():
        if v is None:
            continue
        if isinstance(v, (int, float)):
            if abs(v) >= 1000:
                return f"{v:,.0f}"
            return f"{v:.2f}"
        return str(v)
    return None


def main():
    schema_text = build_schema_description(os.getenv("DB_NAME"))

    plan_path = os.path.join("output", "plan.json")
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    print(f"Loaded plan with {len(plan)} items.\n")

    processed = []
    for i, item in enumerate(plan, 1):
        title = item.get("title", f"Item {i}")
        visual_type = item.get("visual_type", "")
        print(f"[{i}/{len(plan)}] {title} ({visual_type})")

        out = dict(item)
        out["sql"] = ""
        out["insight"] = ""
        out["chart_b64"] = None
        out["kpi_value"] = None
        out["rows"] = []
        out["columns"] = []
        out["raw_data"] = ""
        out["error"] = None

        try:
            sql = ask_for_sql(schema_text, item)
            out["sql"] = sql
            print(f"    SQL: {sql[:80]}{'...' if len(sql) > 80 else ''}")

            if not is_safe_select(sql):
                raise ValueError("SQL failed safety check (must be a single SELECT).")

            rows = run_query(sql)
            print(f"    -> {len(rows)} rows")

            jsonable_rows = []
            for r in rows:
                clean = {}
                for k, v in r.items():
                    if hasattr(v, "isoformat"):
                        clean[k] = v.isoformat()
                    elif isinstance(v, (int, float, str, bool)) or v is None:
                        clean[k] = v
                    else:
                        clean[k] = str(v)
                jsonable_rows.append(clean)

            out["rows"] = jsonable_rows
            out["columns"] = list(jsonable_rows[0].keys()) if jsonable_rows else []
            out["raw_data"] = json.dumps(jsonable_rows[:20], indent=2, ensure_ascii=False)

            if visual_type == "kpi":
                out["kpi_value"] = format_kpi_value(jsonable_rows)
            else:
                out["chart_b64"] = render_chart(item, jsonable_rows)

            out["insight"] = ask_for_insight(item, jsonable_rows)

        except Exception as e:
            print(f"    ERROR: {e}")
            out["error"] = str(e)

        processed.append(out)

    template = Template(HTML_TEMPLATE)
    html = template.render(
        items=processed,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        db_name=os.getenv("DB_NAME"),
    )

    out_path = os.path.join("output", "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()
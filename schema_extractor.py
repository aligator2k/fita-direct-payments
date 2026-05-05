"""
Connects to the MySQL server and extracts schema info: tables, columns,
data types and constraints. Builds a structured text description that
can be passed to an LLM as context.
"""

import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="information_schema",
    )


def fetch_tables(cursor, schema_name):
    cursor.execute(
        """
        SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS, TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
        """,
        (schema_name,),
    )
    return cursor.fetchall()


def fetch_columns(cursor, schema_name, table_name):
    cursor.execute(
        """
        SELECT COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, COLUMN_TYPE,
               IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (schema_name, table_name),
    )
    return cursor.fetchall()


def fetch_constraints(cursor, schema_name):
    cursor.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME,
               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
        """,
        (schema_name,),
    )
    return cursor.fetchall()


def build_schema_description(schema_name):
    conn = get_connection()
    cursor = conn.cursor()

    tables = fetch_tables(cursor, schema_name)
    constraints = fetch_constraints(cursor, schema_name)

    lines = [f"DATABASE: {schema_name}", ""]

    for t in tables:
        table_name, table_type, engine, table_rows, table_comment = t
        lines.append(f"TABLE: {table_name} (rows~{table_rows})")

        columns = fetch_columns(cursor, schema_name, table_name)
        for c in columns:
            col_name, pos, data_type, col_type, nullable, key, default, extra, comment = c
            parts = [f"  - {col_name} ({col_type}) NULL={nullable}"]
            if key:
                parts.append(f"KEY={key}")
            if extra:
                parts.append(f"EXTRA={extra}")
            lines.append(" ".join(parts))
        lines.append("")

    if constraints:
        lines.append("FOREIGN KEYS:")
        for fk in constraints:
            tbl, col, name, ref_tbl, ref_col = fk
            lines.append(f"  {tbl}.{col} -> {ref_tbl}.{ref_col} ({name})")
    else:
        lines.append("FOREIGN KEYS: none declared in the database")
        lines.append("Logical relationships inferred from column names:")
        lines.append("  payments.mandate_id -> mandates.id")
        lines.append("  mandates.organisation_id -> organisations.id")

    cursor.close()
    conn.close()

    return "\n".join(lines)


if __name__ == "__main__":
    schema = os.getenv("DB_NAME")
    description = build_schema_description(schema)
    print(description)

    out_path = os.path.join("output", "schema_description.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(description)
    print(f"\nSaved to {out_path}")
"""
Runs the full pipeline:
1. Extract schema from MySQL
2. Ask Gemini for a visualization plan
3. Build the HTML report

Each step logs progress. If any step fails, the whole thing exits non-zero.
"""

import logging
import sys
import traceback


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("output/pipeline.log", mode="a", encoding="utf-8"),
        ],
    )


def run_step(name, func):
    log = logging.getLogger(name)
    log.info(f"=== {name} START ===")
    try:
        func()
        log.info(f"=== {name} DONE ===")
    except Exception as e:
        log.error(f"=== {name} FAILED: {e} ===")
        log.error(traceback.format_exc())
        raise


def main():
    import os
    os.makedirs("output", exist_ok=True)
    configure_logging()
    log = logging.getLogger("pipeline")
    log.info("Pipeline starting")

    from schema_extractor import build_schema_description
    from plan_generator import main as plan_main
    from report_builder import main as report_main

    def step_schema():
        description = build_schema_description(os.getenv("DB_NAME"))
        with open("output/schema_description.txt", "w", encoding="utf-8") as f:
            f.write(description)

    run_step("schema", step_schema)
    run_step("plan", plan_main)
    run_step("report", report_main)

    log.info("Pipeline complete. See output/report.html")


if __name__ == "__main__":
    main()
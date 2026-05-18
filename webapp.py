"""
Small Flask web app for running the pipeline interactively.
- Home page shows the current status, a form to start a run, and log output
- POST /run starts the pipeline in a background thread
- GET /logs streams the current log file
- GET /report serves the generated report.html if it exists
"""

import os
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, request, send_file, jsonify, abort

app = Flask(__name__)

OUTPUT_DIR = "output"
LOG_FILE = os.path.join(OUTPUT_DIR, "pipeline.log")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.html")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Module-level state to track if a pipeline run is in progress
_state = {
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_error": None,
}
_lock = threading.Lock()


def _run_pipeline_in_thread(num_items: int):
    """Run the pipeline. Sets PLAN_ITEMS env var so plan_generator can read it."""
    try:
        # Pass parameter through env var
        os.environ["PLAN_ITEMS"] = str(num_items)

        # Import here to avoid Flask reloading messing with imports
        from main import main as run_main
        run_main()

        with _lock:
            _state["last_error"] = None
    except Exception as e:
        logging.exception("Pipeline failed")
        with _lock:
            _state["last_error"] = str(e)
    finally:
        with _lock:
            _state["running"] = False
            _state["last_finished"] = datetime.now().isoformat(timespec="seconds")


@app.route("/")
def home():
    with _lock:
        state = dict(_state)
    has_report = os.path.exists(REPORT_FILE)
    return render_template("home.html", state=state, has_report=has_report)


@app.route("/run", methods=["POST"])
def start_run():
    num_items = int(request.form.get("num_items", 7))
    num_items = max(3, min(num_items, 10))  # clamp to sensible range

    with _lock:
        if _state["running"]:
            return jsonify({"ok": False, "error": "Pipeline is already running"}), 409
        _state["running"] = True
        _state["last_started"] = datetime.now().isoformat(timespec="seconds")
        _state["last_error"] = None

    # Truncate the log so this run starts fresh
    try:
        open(LOG_FILE, "w", encoding="utf-8").close()
    except OSError:
        pass

    t = threading.Thread(target=_run_pipeline_in_thread, args=(num_items,), daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    with _lock:
        state = dict(_state)
    state["has_report"] = os.path.exists(REPORT_FILE)
    return jsonify(state)


@app.route("/logs")
def logs():
    if not os.path.exists(LOG_FILE):
        return ""
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/report")
def report():
    if not os.path.exists(REPORT_FILE):
        abort(404)
    return send_file(REPORT_FILE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
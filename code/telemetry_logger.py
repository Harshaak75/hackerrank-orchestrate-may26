import json
import time
from pathlib import Path

# Saves to support_tickets/system_trace.jsonl alongside the output.csv
TRACE_FILE = Path(__file__).parent.parent / "support_tickets" / "system_trace.jsonl"

def init_telemetry() -> None:
    """
    Initializes the telemetry system.
    Clears out the old trace file so we get a fresh auditable log per run.
    """
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TRACE_FILE.exists():
        TRACE_FILE.unlink()

def log_trace(trace_data: dict) -> None:
    """
    Appends a structured JSON telemetry trace to the log.
    Includes timestamps for observability and debugging.
    """
    trace_data["timestamp_utc"] = time.time()
    with TRACE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace_data) + "\n")

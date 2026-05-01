"""
feedback_collector.py
─────────────────────
Provides a lightweight CSAT (Customer Satisfaction) feedback collection
and analytics layer for the support pipeline.

In production this would be triggered by a post-response survey link sent
to the customer.  In this batch-CSV setup it exposes:

  • log_feedback(ticket_id, score, comment)  → appends to feedback.jsonl
  • get_feedback_report()                    → returns aggregate analytics
  • attach_feedback_columns(df)             → adds blank columns to output

Usage (CLI):
    python3 feedback_collector.py --ticket_id 3 --score 2 --comment "Wrong advice"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import OUTPUT_CSV_PATH, REPO_ROOT

FEEDBACK_LOG_PATH = REPO_ROOT / "support_tickets" / "feedback.jsonl"
FEEDBACK_COLUMNS = ["feedback_score", "feedback_comment"]

# Valid CSAT scores
SCORE_RANGE = range(1, 6)  # 1 = very unsatisfied … 5 = very satisfied
SCORE_LABELS = {
    1: "Very Unsatisfied 😡",
    2: "Unsatisfied 😕",
    3: "Neutral 😐",
    4: "Satisfied 🙂",
    5: "Very Satisfied 😄",
}


# ──────────────────────────────────────────────────────────────────────────────
# Core feedback logging
# ──────────────────────────────────────────────────────────────────────────────

def log_feedback(ticket_id: int, score: int, comment: str = "") -> None:
    """Append a single CSAT feedback entry to the JSONL log file.

    Args:
        ticket_id: 0-based row index from output.csv.
        score:     Integer 1-5 (1 = worst, 5 = best).
        comment:   Optional free-text comment from the user.
    """
    if score not in SCORE_RANGE:
        raise ValueError(f"Score must be between 1 and 5, got {score}")

    # Read subject + product_area for context
    subject, product_area, status = "", "", ""
    if OUTPUT_CSV_PATH.exists():
        try:
            df = pd.read_csv(OUTPUT_CSV_PATH)
            if 0 <= ticket_id < len(df):
                row = df.iloc[ticket_id]
                subject = str(row.get("subject", ""))
                product_area = str(row.get("product_area", ""))
                status = str(row.get("status", ""))
        except Exception:
            pass

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticket_id": ticket_id,
        "subject": subject,
        "product_area": product_area,
        "status": status,
        "score": score,
        "label": SCORE_LABELS[score],
        "comment": comment.strip(),
    }

    FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"✅  Feedback recorded — Ticket #{ticket_id} | Score: {score}/5 ({SCORE_LABELS[score]})")


# ──────────────────────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────────────────────

def get_feedback_report() -> dict:
    """Parse feedback.jsonl and return aggregate CSAT analytics."""
    if not FEEDBACK_LOG_PATH.exists():
        return {"error": "No feedback collected yet. Run submit_feedback first."}

    entries = []
    with open(FEEDBACK_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    if not entries:
        return {"error": "feedback.jsonl is empty."}

    scores = [e["score"] for e in entries]
    avg = sum(scores) / len(scores)
    csat_pct = round(sum(1 for s in scores if s >= 4) / len(scores) * 100, 1)

    # Per product_area breakdown
    area_scores: dict[str, list[int]] = {}
    for e in entries:
        area = e.get("product_area", "unknown")
        area_scores.setdefault(area, []).append(e["score"])
    area_avgs = {area: round(sum(v) / len(v), 2) for area, v in area_scores.items()}

    # Per status breakdown
    status_scores: dict[str, list[int]] = {}
    for e in entries:
        s = e.get("status", "unknown")
        status_scores.setdefault(s, []).append(e["score"])
    status_avgs = {s: round(sum(v) / len(v), 2) for s, v in status_scores.items()}

    # Worst responses (score <= 2)
    worst = [
        {"ticket_id": e["ticket_id"], "subject": e["subject"], "score": e["score"], "comment": e["comment"]}
        for e in entries if e["score"] <= 2
    ]

    return {
        "total_responses": len(entries),
        "average_score": round(avg, 2),
        "csat_percent": csat_pct,  # % of users who rated 4 or 5
        "score_distribution": {str(i): scores.count(i) for i in SCORE_RANGE},
        "by_product_area": area_avgs,
        "by_status": status_avgs,
        "worst_responses": worst,
    }


def print_report() -> None:
    """Print a formatted CSAT report to stdout."""
    report = get_feedback_report()
    if "error" in report:
        print(f"⚠️  {report['error']}")
        return

    print("\n" + "═" * 55)
    print("  📊  CSAT FEEDBACK REPORT")
    print("═" * 55)
    print(f"  Total responses rated : {report['total_responses']}")
    print(f"  Average score         : {report['average_score']} / 5.0")
    print(f"  CSAT (score ≥ 4)      : {report['csat_percent']}%")
    print()

    print("  Score distribution:")
    for score, count in report["score_distribution"].items():
        bar = "█" * count
        print(f"    {score} ★  {bar} ({count})")
    print()

    print("  By product area:")
    for area, avg in sorted(report["by_product_area"].items(), key=lambda x: x[1]):
        flag = " ⚠️ " if avg < 3.0 else ""
        print(f"    {area:<30} {avg:.2f}{flag}")
    print()

    print("  By status (replied vs escalated):")
    for status, avg in report["by_status"].items():
        print(f"    {status:<15} avg={avg:.2f}")
    print()

    if report["worst_responses"]:
        print("  🔴 Low-rated responses (score ≤ 2):")
        for w in report["worst_responses"]:
            print(f"    Ticket #{w['ticket_id']} — {w['subject']!r}")
            if w["comment"]:
                print(f"       Comment: {w['comment']}")
    else:
        print("  ✅ No low-rated responses (score ≤ 2).")

    print("═" * 55 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# Output CSV integration
# ──────────────────────────────────────────────────────────────────────────────

def attach_feedback_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add blank feedback columns to the output DataFrame if not present.

    These columns are intentionally left empty — they are filled in later
    via log_feedback() when users rate their support experience.
    """
    for col in FEEDBACK_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Record CSAT feedback for a processed support ticket.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    # submit
    submit = sub.add_parser("submit", help="Submit feedback for a ticket")
    submit.add_argument("--ticket_id", type=int, required=True, help="Row index in output.csv (0-based)")
    submit.add_argument("--score", type=int, required=True, choices=list(SCORE_RANGE),
                        help="1=Very Unsatisfied … 5=Very Satisfied")
    submit.add_argument("--comment", type=str, default="", help="Optional free-text comment")

    # report
    sub.add_parser("report", help="Print the aggregate CSAT report")

    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "submit":
        log_feedback(ticket_id=args.ticket_id, score=args.score, comment=args.comment)
    elif args.command == "report":
        print_report()
    else:
        parser.print_help()
        sys.exit(1)

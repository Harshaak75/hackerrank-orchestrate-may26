from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
GEMINI_MIN_SECONDS_BETWEEN_REQUESTS = float(
    os.getenv("GEMINI_MIN_SECONDS_BETWEEN_REQUESTS", "12.5")
)
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "6"))

DATA_DIR = REPO_ROOT / "data"
INPUT_CSV_PATH = REPO_ROOT / "support_tickets" / "support_tickets.csv"
OUTPUT_CSV_PATH = REPO_ROOT / "support_tickets" / "output.csv"

COMPANY_DATA_DIRS = {
    "HackerRank": DATA_DIR / "hackerrank",
    "Claude": DATA_DIR / "claude",
    "Visa": DATA_DIR / "visa",
}

OUTPUT_COLUMNS = [
    "issue",
    "subject",
    "company",
    "response",
    "product_area",
    "status",
    "request_type",
    "justification",
    "confidence_score",
]

DANGER_KEYWORDS = [
    # Prompt injection / jailbreak attempts
    "ignore previous instructions",
    "system prompt",
    "developer message",
    "reveal hidden prompt",
    "bypass safety",
    "disable guardrails",
    "logic exact",
    "internal rules",
    "display all the rules",
    # Malware / exploit
    "malware",
    "exploit",
    "hack into",
    "delete all files from the system",
    # Financial fraud / card security
    "stolen card",
    "fraud",
    "chargeback",
    "bank account",
    "cvv",
    "pin number",
    # Unauthorized account access
    "password reset for someone else",
    "restore my access immediately",
    "not the workspace owner",
    "not the owner",
    "not the admin",
    # Security disclosure
    "security vulnerability",
    "bug bounty",
]

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "that",
    "the",
    "their",
    "this",
    "to",
    "we",
    "with",
    "you",
    "your",
}

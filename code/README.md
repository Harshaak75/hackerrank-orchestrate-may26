# Support Agent

1. Create and activate a virtual environment in [`code/`](/Users/dotspeaks/Documents/hackerrank-orchestrate-may26/code): `python3 -m venv venv && source venv/bin/activate` on macOS/Linux or `venv\\Scripts\\activate` on Windows.
2. Install dependencies and add your Gemini settings: `pip install -r requirements.txt` and then copy `.env.example` to `.env`, fill in `GEMINI_API_KEY`, and optionally override `GEMINI_MODEL`.
3. Run the agent with `python3 main.py`; it will read [`support_tickets/support_tickets.csv`](/Users/dotspeaks/Documents/hackerrank-orchestrate-may26/support_tickets/support_tickets.csv) and write [`support_tickets/output.csv`](/Users/dotspeaks/Documents/hackerrank-orchestrate-may26/support_tickets/output.csv).

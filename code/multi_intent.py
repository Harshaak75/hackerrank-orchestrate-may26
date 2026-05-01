def extract_intents(text: str) -> list[str]:
    text = text.lower()
    intents = []
    
    # Highest risk first
    if any(kw in text for kw in {"lock", "hack", "stolen", "access", "login", "password", "seat", "admin", "unauthorized"}):
        intents.append("account_access")
        
    if any(kw in text for kw in {"payment", "refund", "charge", "billing", "money", "card", "invoice", "dispute"}):
        intents.append("payment_issue")
        
    if any(kw in text for kw in {"privacy", "data", "train", "crawler", "bot", "opt out"}):
        intents.append("data_privacy")
        
    if any(kw in text for kw in {"error", "fail", "not working", "broken", "bug", "glitch", "crash"}):
        intents.append("technical_issue")
        
    if any(kw in text for kw in {"how to", "where can i", "setup", "configure", "create", "update"}):
        intents.append("how_to")

    if not intents:
        intents.append("general_inquiry")
        
    return intents

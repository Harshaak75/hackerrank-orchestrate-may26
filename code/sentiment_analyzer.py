def is_highly_frustrated(text: str) -> bool:
    """
    Detects strong negative sentiment or extreme frustration in a customer ticket.
    This is used to trigger VIP Urgency Routing and empathetic responses.
    """
    text = text.lower()
    frustration_keywords = {
        "ridiculous", "unacceptable", "terrible", "worst", "angry",
        "furious", "frustrated", "upset", "pissed", "ruined", "mad",
        "scam", "awful", "pathetic", "garbage", "trash", "disgusting",
        "horrible", "hate", "unprofessional", "waste of time"
    }
    return any(kw in text for kw in frustration_keywords)

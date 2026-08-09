def should_require_web_search(content: str) -> bool:
    text = content.lower()

    web_search_signals = [
        "current",
        "latest",
        "today",
        "news",
        "recent",
        "right now",
        "check internet",
        "on the internet",
        "online",
        "stock price",
        "weather",
        "score",
    ]

    return any(signal in text for signal in web_search_signals)
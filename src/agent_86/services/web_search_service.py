class WebSearchService:
    async def search(self, query: str) -> tuple[str, dict]:
        return (
            "WEB SEARCH PROVIDER NOT CONFIGURED.\n"
            f"Requested query: {query}\n"
            "No live web results were retrieved.",
            {
                "provider": "none",
                "query": query,
                "status": "not_configured",
            },
        )
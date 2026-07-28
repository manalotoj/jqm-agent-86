from fastapi import FastAPI


app = FastAPI(title="agent-86")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

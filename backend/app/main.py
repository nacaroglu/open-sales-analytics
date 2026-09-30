from fastapi import FastAPI

app = FastAPI(title="Open Sales Analytics")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

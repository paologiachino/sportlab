"""sportlab FastAPI application."""

from fastapi import FastAPI

app = FastAPI(title="sportlab")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness check: the process is up and answering requests."""
    return {"status": "ok"}

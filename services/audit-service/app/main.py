from fastapi import FastAPI

app = FastAPI(title="Audit Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

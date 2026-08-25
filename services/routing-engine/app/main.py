from fastapi import FastAPI

app = FastAPI(title="Routing Engine")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

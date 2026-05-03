from fastapi import FastAPI

app = FastAPI(
    title="Image Insight API",
    description="Backend API for local-first media metadata analytics.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

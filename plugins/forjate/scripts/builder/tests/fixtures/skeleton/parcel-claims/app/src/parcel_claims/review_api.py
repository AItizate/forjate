from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz")
def readyz() -> dict:
    return {"ok": True}


@app.get("/drafts")
def drafts() -> list:
    # SEAM review-surface: list drafts and take the clerk's decision (backlog, Walk)
    raise NotImplementedError("backlog ticket T-review-surface")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

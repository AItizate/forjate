from fastapi import FastAPI

app = FastAPI()
SHIPMENTS = {f"T{i}": {"tracking": f"T{i}", "status": "delivered"} for i in range(10)}
CALLS: list[str] = []


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz")
def readyz() -> dict:
    return {"ok": True}


@app.get("/shipments/{tracking}")
def shipment(tracking: str) -> dict:
    CALLS.append(tracking)
    return SHIPMENTS[tracking]


@app.get("/calls")
def calls() -> dict:
    return {"count": len(CALLS)}


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()

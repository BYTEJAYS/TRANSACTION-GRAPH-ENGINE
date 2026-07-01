"""Run UB as a standalone FastAPI service:  python -m ub_service  (uvicorn :8000)."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("ub_service.app:app", host="0.0.0.0",
                port=int(os.environ.get("UB_PORT", "8000")), log_level="info")

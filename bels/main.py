"""
BELS standalone FastAPI application.

Run:  python -m bels.main          (from ~/Desktop/TGIE)
or:   uvicorn bels.main:app --port 8200

Serves the JSON API at the root paths from the spec and the matte-black dashboard at /.
The same `router` (bels.api) can instead be mounted into the main TGIE backend under
config.API_PREFIX (/bels) for in-process integration.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from . import __version__, config
from .api import router

config.ensure_dirs()

app = FastAPI(
    title="TGIE Blockchain Evidence Ledger System (BELS)",
    version=__version__,
    description="Immutable, blockchain-anchored fraud-evidence registry, verification "
                "and chain-of-custody platform for the TGIE ecosystem.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

_DASHBOARD = Path(__file__).resolve().parent / "dashboard" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    if _DASHBOARD.exists():
        return FileResponse(_DASHBOARD)
    return HTMLResponse("<h1>BELS</h1><p>Dashboard not found. API is live at /health.</p>")


def main() -> None:
    import uvicorn
    print(f"⛓  BELS starting on http://{config.HOST}:{config.PORT}  (provider={config.BLOCKCHAIN_PROVIDER})")
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()

"""Mount the Vite-built SPA at /app and serve index.html for any
sub-path so React Router can handle client-side routing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

SPA_DIR = Path("src/web/static/app")
INDEX_HTML = SPA_DIR / "index.html"

router = APIRouter()


def mount_spa(app) -> None:
    """Mount /app/assets static files + catch-all route returning index.html."""
    if (SPA_DIR / "assets").exists():
        app.mount(
            "/app/assets",
            StaticFiles(directory=str(SPA_DIR / "assets")),
            name="spa-assets",
        )

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{rest:path}", include_in_schema=False)
    async def spa_index(request: Request, rest: str = "") -> FileResponse:
        if not INDEX_HTML.exists():
            return FileResponse(
                "src/web/templates/spa-missing.html", status_code=503
            )
        return FileResponse(INDEX_HTML)

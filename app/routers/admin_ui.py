"""Minimal admin UI for managing bot tokens. No build step, no external assets."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_PAGE_PATH = Path(__file__).parent / "admin_bots.html"


@router.get("/admin/bots", response_class=HTMLResponse, include_in_schema=False)
async def bots_admin_page() -> HTMLResponse:
    """Token management page: list, create and revoke bot tokens."""
    return HTMLResponse(_PAGE_PATH.read_text(encoding="utf-8"))

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import BASE_DIR


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"page_title": "Relay Master | Overview"},
    )


@router.get("/control", response_class=HTMLResponse)
def control_panel(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"page_title": "Relay Master | Control Panel"},
    )

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from pa_investing.analytics_app.pages import portfolio_page, signal_page

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/analysis/portfolio", response_class=HTMLResponse)
def portfolio_analysis() -> str:
    return portfolio_page()


@router.get("/analysis/signal/{signal_id}", response_class=HTMLResponse)
def signal_analysis(signal_id: str) -> str:
    return signal_page(signal_id)

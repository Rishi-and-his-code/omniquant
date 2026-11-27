"""AI strategy generation routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.strategy import AIGenerateStrategyRequest, AIGenerateStrategyResponse
from app.services.ai_provider import AIModelProvider, AIProviderError

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status() -> dict:
    settings = get_settings()
    return {
        "ai_enabled": settings.ai_enabled,
        "ai_configured": settings.ai_configured,
        "ai_fallback_configured": settings.ai_fallback_configured,
        "model": settings.ai_model or settings.ai_fallback_model or None,
    }


def _http_status_for_ai(code: str) -> int:
    if code in {"AI_UNAVAILABLE", "AI_UNREACHABLE", "AI_TIMEOUT", "AI_RATE_LIMITED"}:
        return 503
    return 502


@router.post("/generate-strategy", response_model=AIGenerateStrategyResponse)
def generate_strategy(body: AIGenerateStrategyRequest) -> AIGenerateStrategyResponse:
    provider = AIModelProvider()
    try:
        result = provider.generate_strategy(body.prompt)
        return AIGenerateStrategyResponse(**result)
    except AIProviderError as exc:
        raise HTTPException(
            status_code=_http_status_for_ai(exc.code),
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        ) from exc

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


@router.post("/generate-strategy", response_model=AIGenerateStrategyResponse)
def generate_strategy(body: AIGenerateStrategyRequest) -> AIGenerateStrategyResponse:
    provider = AIModelProvider()
    try:
        result = provider.generate_strategy(body.prompt)
        return AIGenerateStrategyResponse(**result)
    except AIProviderError as exc:
        if exc.code == "AI_UNAVAILABLE":
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": exc.message, "details": exc.details},
            ) from exc
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        ) from exc

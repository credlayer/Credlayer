"""Wallet reputation scoring endpoints."""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from credlayer.api.deps import get_db_session
from credlayer.api.envelope import Envelope, ok
from credlayer.core.config import get_settings
from credlayer.schemas.common import CamelModel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scores", tags=["scores"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class WalletScore(CamelModel):
    """Single wallet reputation score returned by the scoring endpoint."""

    address: str
    trust_score: int = Field(..., ge=0, le=1000)
    trust_level: str
    risk_level: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    fraud_probability: float = Field(..., ge=0.0, le=1.0)
    network: str = "solana"
    explanation: str


class BatchScoreRequest(BaseModel):
    """Request body for batch scoring."""

    addresses: list[str] = Field(..., min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/{address}",
    response_model=Envelope[WalletScore],
    summary="Score a single wallet",
    description="Query the standalone ML microservice for the GNN-derived trust score.",
)
async def score_wallet(address: str) -> Envelope[WalletScore]:
    settings = get_settings()
    url = f"{settings.ml_service_url.rstrip('/')}/api/v1/scores/{address}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                body = response.json()
                data = body.get("data", body)
                validated_score = WalletScore.model_validate(data)

                # --- Post the relayer to mint on-chain attestation ---
                relayer_url = f"{settings.relayer_service_url.rstrip('/')}/api/v1/attestations/issue"

                # the relayer expects the riskLevel as uppercase (LOW, MEDIUM, HIGH)
                risk_level_upper = validated_score.risk_level.upper()

                relayer_payload = {
                    "targetWallet": validated_score.address,
                    "trustScore": validated_score.trust_score,
                    "riskLevel": risk_level_upper,
                }

                try:
                    relayer_resp = await client.post(relayer_url, json=relayer_payload)
                    if relayer_resp.status_code == 200:
                        tx_hash = relayer_resp.json().get("txHash")
                        logger.info("attestation_minted", tx_hash=tx_hash)
                    else:
                        logger.error("relayer_mint_failed", status=relayer_resp.status_code, error=relayer_resp.text)
                except Exception as e:
                    logger.error("relayer_unreachable", url=relayer_url, error=str(e))

                return ok(validated_score)
            else:
                logger.warning("ml_service_non_200", status_code=response.status_code, text=response.text)
    except Exception as exc:
        logger.warning(
            "ml_service_unreachable_fallback",
            address=address,
            url=url,
            error=repr(exc),
        )
        fallback_data = WalletScore(
            address=address,
            trust_score=500,
            trust_level="low",
            risk_level="medium",
            confidence=0.0,
            fraud_probability=0.5,
            network="solana",
            explanation=f"ML service connection error to {url}: {type(exc).__name__} ({exc})",
        )
        return ok(fallback_data)

    fallback_data = WalletScore(
        address=address,
        trust_score=500,
        trust_level="low",
        risk_level="medium",
        confidence=0.0,
        fraud_probability=0.5,
        network="solana",
        explanation=f"ML service returned non-200 status code from {url}.",
    )
    return ok(fallback_data)


@router.post(
    "/batch",
    response_model=Envelope[list[WalletScore]],
    summary="Score multiple wallets in batch",
    description="Batch scoring via the standalone ML microservice.",
)
async def score_batch(body: BatchScoreRequest) -> Envelope[list[WalletScore]]:
    settings = get_settings()
    url = f"{settings.ml_service_url.rstrip('/')}/api/v1/scores/batch"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json={"addresses": body.addresses})
            if response.status_code == 200:
                body_data = response.json()
                data = body_data.get("data", body_data)
                scores = [WalletScore.model_validate(item) for item in data]
                return ok(scores)
            else:
                logger.warning("ml_service_non_200", status_code=response.status_code, text=response.text)
    except Exception as exc:
        logger.warning(
            "ml_service_unreachable_fallback",
            addresses=body.addresses,
            url=url,
            error=repr(exc),
        )

    fallback_scores = [
        WalletScore(
            address=addr,
            trust_score=500,
            trust_level="low",
            risk_level="medium",
            confidence=0.0,
            fraud_probability=0.5,
            network="solana",
            explanation="ML service unavailable; fallback score returned.",
        )
        for addr in body.addresses
    ]
    return ok(fallback_scores)

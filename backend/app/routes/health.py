import os

from fastapi import APIRouter, Response

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Liveness: is the process up?

    Deliberately cheap and dependency-free. A load balancer restarts the
    container when this fails, so making it depend on HenrikDev or Anthropic
    would turn someone else's outage into a restart loop of our own. ECS Express
    Mode points --health-check-path here.
    """
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response):
    """Readiness: is this instance configured well enough to serve?

    Reports configuration shape only -- no network calls, so polling it is free
    and it never fails for a reason outside this box. Returns 503 when a
    required key is missing, which is the state where the app is running but
    half the product returns 502s.
    """
    from app.services import rag_service

    checks = {
        # Accepts the legacy RIOT_API_KEY name during the SSM migration.
        "match_provider_configured": bool(
            os.getenv("HENRIK_API_KEY") or os.getenv("RIOT_API_KEY")
        ),
        "claude_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        # RAG is an optional feature: absent means /meta degrades, not that the
        # service is unhealthy, so it is reported but does not drive the status.
        "rag_available": rag_service.is_available(),
    }

    degraded = not (checks["match_provider_configured"] and checks["claude_configured"])
    if degraded:
        response.status_code = 503

    return {
        "status": "degraded" if degraded else "ready",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "checks": checks,
    }

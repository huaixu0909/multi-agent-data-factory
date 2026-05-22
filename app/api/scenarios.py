from fastapi import APIRouter

from app.core.models import ScenarioListResponse
from app.core.registry import registry


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.get("", response_model=ScenarioListResponse)
def list_scenarios() -> ScenarioListResponse:
    items = registry.list_descriptors()
    return ScenarioListResponse(items=items, total=len(items))


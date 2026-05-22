from fastapi import APIRouter, Query

from app.core.database import list_personas
from app.core.models import PersonaListResponse, PersonaRecord


router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("", response_model=PersonaListResponse)
def get_personas(scenario: str | None = Query(default=None)) -> PersonaListResponse:
    items = list_personas(scenario=scenario)
    return PersonaListResponse(items=items, total=len(items))


@router.get("/{persona_id}", response_model=PersonaRecord)
def get_persona(persona_id: str) -> PersonaRecord:
    for persona in list_personas():
        if persona.persona_id == persona_id:
            return persona
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Persona not found")

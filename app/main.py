from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.conversations import router as conversations_router
from app.api.datasets import router as datasets_router
from app.api.personas import router as personas_router
from app.api.scenarios import router as scenarios_router
from app.api.simulations import router as simulations_router
from app.core.config import APP_VERSION
from app.core.database import ensure_data_dirs
from app.core.models import HealthResponse
from app.core.registry import registry
from app.scenarios.code_review import code_review_scenario
from app.scenarios.customer_complaint import customer_complaint_scenario
from app.scenarios.technical_interview import technical_interview_scenario


def create_app() -> FastAPI:
    registry.register(code_review_scenario)
    registry.register(customer_complaint_scenario)
    registry.register(technical_interview_scenario)

    application = FastAPI(
        title="Multi-Agent Synthetic Data Factory",
        description="A local MVP for multi-agent social simulation data generation.",
        version=APP_VERSION,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(scenarios_router)
    application.include_router(simulations_router)
    application.include_router(conversations_router)
    application.include_router(datasets_router)
    application.include_router(personas_router)

    @application.on_event("startup")
    def on_startup() -> None:
        ensure_data_dirs()

    @application.get("/")
    def read_root() -> dict[str, str]:
        return {
            "name": "Multi-Agent Synthetic Data Factory",
            "status": "running",
            "version": APP_VERSION,
            "docs": "http://localhost:8001/docs",
            "health": "http://localhost:8001/health",
            "scenarios": "http://localhost:8001/api/scenarios",
        }

    @application.get("/health", response_model=HealthResponse)
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="multi-agent-data-factory",
            version=APP_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    return application


app = create_app()

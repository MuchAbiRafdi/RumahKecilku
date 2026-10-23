from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import activities, ai, attendance, auth, children, development, kpsp, meals, messages, notifications, observations, sensors
from app.core.middleware import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from app.core.runtime import RuntimeSettings
from app.repositories.activity_repository import ActivityRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.development_report_repository import DevelopmentReportRepository
from app.repositories.kpsp_repository import KpspRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.observation_repository import ObservationRepository
from app.repositories.sensor_repository import SensorRepository
from app.repositories.stimulation_repository import StimulationRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "rumah_kecilku.sqlite3"


def create_app(database_path: str | Path | None = None) -> FastAPI:
    settings = RuntimeSettings.from_env()
    configured_database_path = database_path or os.getenv("RUMAH_DB_PATH")
    if settings.demo_sample_data and not configured_database_path:
        raise RuntimeError("RUMAH_DEMO_SAMPLE_DATA=1 memerlukan RUMAH_DB_PATH eksplisit untuk database preview yang terpisah.")
    db_path = Path(configured_database_path or DEFAULT_DB_PATH)
    if settings.demo_sample_data and db_path.resolve() == DEFAULT_DB_PATH.resolve():
        raise RuntimeError("Data observasi sintetis tidak boleh di-seed ke database default yang persisten.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Keep newly created SQLite, WAL, and temporary files private to the service account.
        if os.name == "posix":
            os.umask(0o077)
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        repository = KpspRepository(db_path)
        repository.initialize()
        if settings.demo_sample_data:
            repository.seed_demo_samples()
        auth_repository = AuthRepository(db_path)
        auth_repository.initialize(include_demo_accounts=settings.demo_mode)
        auth_repository.prune_expired_sessions()
        activity_repository = ActivityRepository(db_path)
        activity_repository.initialize()
        if settings.demo_sample_data:
            activity_repository.seed_demo_samples()
        message_repository = MessageRepository(db_path)
        message_repository.initialize()
        notification_repository = NotificationRepository(db_path)
        notification_repository.initialize()
        sensor_repository = SensorRepository(db_path)
        sensor_repository.initialize()
        attendance_repository = AttendanceRepository(db_path)
        attendance_repository.initialize()
        observation_repository = ObservationRepository(db_path)
        observation_repository.initialize()
        if settings.demo_sample_data:
            observation_repository.seed_demo_samples()
        meal_repository = MealRepository(db_path)
        meal_repository.initialize()
        development_report_repository = DevelopmentReportRepository(db_path)
        development_report_repository.initialize()
        stimulation_repository = StimulationRepository(db_path)
        stimulation_repository.initialize()
        if os.name == "posix" and db_path.exists():
            db_path.chmod(0o600)

        app.state.kpsp_repository = repository
        app.state.auth_repository = auth_repository
        app.state.activity_repository = activity_repository
        app.state.message_repository = message_repository
        app.state.notification_repository = notification_repository
        app.state.sensor_repository = sensor_repository
        app.state.attendance_repository = attendance_repository
        app.state.observation_repository = observation_repository
        app.state.meal_repository = meal_repository
        app.state.development_report_repository = development_report_repository
        app.state.stimulation_repository = stimulation_repository
        yield

    docs_enabled = settings.app_env != "production"
    application = FastAPI(
        title="Rumah Kecilku API",
        version="0.1.0",
        description=(
            "API untuk pencatatan aktivitas, notifikasi dan pengingat keluarga, katalog gizi bersumber, "
            "telemetri sensor ruang, formulir KPSP usia 3–72 bulan, dan insight lokal transparan."
        ),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = settings
    # Middleware is added in this order so security headers also cover rejected requests.
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=settings.max_request_body_bytes,
    )
    application.add_middleware(SecurityHeadersMiddleware, app_env=settings.app_env)

    application.include_router(auth.router, prefix="/api")
    application.include_router(activities.router, prefix="/api")
    application.include_router(attendance.router, prefix="/api")
    application.include_router(children.router, prefix="/api")
    application.include_router(messages.router, prefix="/api")
    application.include_router(notifications.router, prefix="/api")
    application.include_router(sensors.router, prefix="/api")
    application.include_router(observations.router, prefix="/api")
    application.include_router(kpsp.router, prefix="/api")
    application.include_router(meals.router, prefix="/api")
    application.include_router(ai.router, prefix="/api")
    application.include_router(development.router, prefix="/api")

    @application.get("/", tags=["Health"])
    def root() -> dict[str, str | None]:
        return {
            "service": "Rumah Kecilku API",
            "health": "/api/health",
            "docs": "/docs" if docs_enabled else None,
        }

    @application.get("/api/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "rumah-kecilku-python-api", "version": "0.1.0"}

    return application


app = create_app()

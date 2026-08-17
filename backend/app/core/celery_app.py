"""
app/core/celery_app.py
----------------------
Celery application instance.

Imported by worker processes and by FastAPI when queueing tasks.
The task modules are auto-discovered from app.tasks.
"""

import ssl

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
import app.models  # noqa: F401 — register all ORM models for relationship resolution

celery_app = Celery(
    "recalce",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.ingest",
        "app.tasks.match",
        "app.tasks.ml_triage",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=600,
    task_time_limit=660,
)

if settings.CELERY_BROKER_URL.startswith("rediss://"):
    celery_app.conf.update(
        broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
        redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )


@worker_process_init.connect
def _load_ml_models(**kwargs) -> None:
    """
    Load both IsolationForest models into memory when a Celery worker process
    starts up.

    This signal fires once per worker process, not once per task. Loading the
    models here means the ml_triage task never pays the disk-read cost during
    normal operation. The models are held in module-level globals inside
    app/services/anomaly_service.py and are shared across all tasks executed
    by the same process.

    If the model files do not exist (e.g. the developer has not run
    `python ml/train.py` yet), a warning is logged but the worker still starts
    successfully. The ml_triage task will log an error and skip scoring for
    any batch processed before the models are available.
    """
    from app.services.anomaly_service import load_models
    import logging
    logger = logging.getLogger(__name__)
    try:
        load_models()
    except FileNotFoundError as exc:
        logger.warning(
            "ML models could not be loaded at worker startup: %s. "
            "Anomaly scoring will be skipped until models are available.",
            exc,
        )

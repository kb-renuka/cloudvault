from celery import Celery

from app.config import settings

celery = Celery("cloudvault", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])

celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "detect-stuck-jobs": {
            "task": "app.tasks.detect_stuck_jobs",
            "schedule": 60.0,
        }
    },
)

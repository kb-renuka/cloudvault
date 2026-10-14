from datetime import timedelta

from sqlalchemy import func, select

from app import storage
from app.celery_app import celery
from app.config import settings
from app.db import SessionLocal
from app.models import BackupJob, FileVersion, JobStatus, utcnow


def staging_key(job_id: int) -> str:
    return f"staging/{job_id}"


def version_key(file_id: int, version_number: int) -> str:
    return f"files/{file_id}/v{version_number}"


@celery.task(bind=True, max_retries=3)
def process_backup(self, job_id: int):
    with SessionLocal() as db:
        job = db.get(BackupJob, job_id)
        if job is None or job.status == JobStatus.SUCCESS:
            return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = utcnow()
        db.commit()

        try:
            checksum, size = storage.sha256_and_size(staging_key(job.id))

            latest = db.execute(
                select(FileVersion)
                .where(FileVersion.file_id == job.file_id)
                .order_by(FileVersion.version_number.desc())
                .limit(1)
            ).scalar_one_or_none()

            if latest is not None and latest.sha256 == checksum:
                # Unchanged file: no new version needed.
                job.version_id = latest.id
            else:
                next_number = (
                    db.execute(
                        select(func.coalesce(func.max(FileVersion.version_number), 0)).where(
                            FileVersion.file_id == job.file_id
                        )
                    ).scalar_one()
                    + 1
                )
                key = version_key(job.file_id, next_number)
                storage.copy_object(staging_key(job.id), key)
                version = FileVersion(
                    file_id=job.file_id,
                    version_number=next_number,
                    s3_key=key,
                    size_bytes=size,
                    sha256=checksum,
                )
                db.add(version)
                db.flush()
                job.version_id = version.id

            storage.delete_object(staging_key(job.id))
            job.status = JobStatus.SUCCESS
            job.error = None
            job.finished_at = utcnow()
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(BackupJob, job_id)
            job.error = str(exc)[:2000]
            if self.request.retries < self.max_retries:
                job.status = JobStatus.PENDING
                db.commit()
                raise self.retry(exc=exc, countdown=5 * 2**self.request.retries)
            job.status = JobStatus.FAILED
            job.finished_at = utcnow()
            db.commit()


@celery.task
def detect_stuck_jobs():
    """Mark jobs that have been RUNNING too long as FAILED (e.g. the worker crashed)."""
    cutoff = utcnow() - timedelta(minutes=settings.stuck_job_minutes)
    with SessionLocal() as db:
        stuck = db.execute(
            select(BackupJob).where(BackupJob.status == JobStatus.RUNNING, BackupJob.started_at < cutoff)
        ).scalars().all()
        for job in stuck:
            job.status = JobStatus.FAILED
            job.error = f"Job stuck in RUNNING for over {settings.stuck_job_minutes} minutes"
            job.finished_at = utcnow()
        db.commit()
        return len(stuck)

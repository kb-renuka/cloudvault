from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.config import settings
from app.db import Base, engine, get_db
from app.models import BackupFile, BackupJob, FileVersion, JobStatus
from app.schemas import DownloadOut, FileOut, JobOut, RestoreIn, VersionOut
from app.tasks import process_backup, staging_key, version_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # Replace with Alembic migrations later
    storage.ensure_bucket()
    yield


app = FastAPI(title="CloudVault", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/backups", response_model=JobOut, status_code=202)
def create_backup(
    path: str = Form(..., description="Logical path of the file, e.g. docs/report.pdf"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    backup_file = db.execute(select(BackupFile).where(BackupFile.path == path)).scalar_one_or_none()
    if backup_file is None:
        backup_file = BackupFile(path=path)
        db.add(backup_file)
        db.flush()

    job = BackupJob(file_id=backup_file.id)
    db.add(job)
    db.flush()

    try:
        storage.upload_fileobj(file.file, staging_key(job.id))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {exc}")

    db.commit()
    process_backup.delay(job.id)
    return job


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(status: JobStatus | None = None, limit: int = 50, db: Session = Depends(get_db)):
    query = select(BackupJob).order_by(BackupJob.id.desc()).limit(min(limit, 200))
    if status is not None:
        query = query.where(BackupJob.status == status)
    return db.execute(query).scalars().all()


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.FAILED:
        raise HTTPException(409, "Only FAILED jobs can be retried")
    job.status = JobStatus.PENDING
    job.error = None
    db.commit()
    process_backup.delay(job.id)
    return job


@app.get("/files", response_model=list[FileOut])
def list_files(db: Session = Depends(get_db)):
    return db.execute(select(BackupFile).order_by(BackupFile.path)).scalars().all()


@app.get("/files/{file_id}/versions", response_model=list[VersionOut])
def list_versions(file_id: int, db: Session = Depends(get_db)):
    if db.get(BackupFile, file_id) is None:
        raise HTTPException(404, "File not found")
    return db.execute(
        select(FileVersion).where(FileVersion.file_id == file_id).order_by(FileVersion.version_number)
    ).scalars().all()


def _get_version(db: Session, file_id: int, version_number: int) -> FileVersion:
    version = db.execute(
        select(FileVersion).where(
            FileVersion.file_id == file_id, FileVersion.version_number == version_number
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(404, "Version not found")
    return version


@app.get("/files/{file_id}/versions/{version_number}/download", response_model=DownloadOut)
def download_version(file_id: int, version_number: int, db: Session = Depends(get_db)):
    version = _get_version(db, file_id, version_number)
    return DownloadOut(
        url=storage.presigned_url(version.s3_key), expires_in_seconds=settings.presign_expiry_seconds
    )


@app.post("/files/{file_id}/restore", response_model=VersionOut)
def restore_version(file_id: int, body: RestoreIn, db: Session = Depends(get_db)):
    """Restore an old version by copying it forward as the newest version (history is never rewritten)."""
    source = _get_version(db, file_id, body.version_number)
    next_number = (
        db.execute(
            select(func.coalesce(func.max(FileVersion.version_number), 0)).where(
                FileVersion.file_id == file_id
            )
        ).scalar_one()
        + 1
    )
    key = version_key(file_id, next_number)
    storage.copy_object(source.s3_key, key)
    restored = FileVersion(
        file_id=file_id,
        version_number=next_number,
        s3_key=key,
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    db.add(restored)
    db.commit()
    return restored

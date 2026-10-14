from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import JobStatus


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    size_bytes: int
    sha256: str
    created_at: datetime


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    created_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    status: JobStatus
    attempts: int
    error: str | None
    version_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RestoreIn(BaseModel):
    version_number: int


class DownloadOut(BaseModel):
    url: str
    expires_in_seconds: int

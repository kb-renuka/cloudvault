from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://cloudvault:cloudvault@db:5432/cloudvault"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_bucket: str = "cloudvault"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    stuck_job_minutes: int = 10
    presign_expiry_seconds: int = 300


settings = Settings()

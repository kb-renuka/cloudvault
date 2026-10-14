# CloudVault

Cloud backup and disaster-recovery backend: upload files, keep every version, detect failed jobs, restore any version.

**Stack:** Python · FastAPI · PostgreSQL · Redis · Celery · S3 (MinIO locally) · Docker

## Run it

```bash
docker compose up --build
```

- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001 (minioadmin / minioadmin)

## Try it

```bash
# 1. Back up a file (returns a job)
curl -F "path=docs/notes.txt" -F "file=@notes.txt" http://localhost:8000/backups

# 2. Check the job
curl http://localhost:8000/jobs/1

# 3. List files and versions
curl http://localhost:8000/files
curl http://localhost:8000/files/1/versions

# 4. Edit notes.txt, back it up again -> version 2. Re-upload unchanged -> no new version (checksum dedupe).

# 5. Restore version 1 (copied forward as a new version)
curl -X POST -H "Content-Type: application/json" -d '{"version_number":1}' http://localhost:8000/files/1/restore

# 6. Get a presigned download link
curl http://localhost:8000/files/1/versions/1/download

# 7. See failed jobs, retry one
curl "http://localhost:8000/jobs?status=FAILED"
curl -X POST http://localhost:8000/jobs/1/retry
```

## How it works

1. `POST /backups` streams the upload to a staging key in S3, records a `PENDING` job, and queues a Celery task.
2. The worker computes SHA-256, skips unchanged files, otherwise copies the object to `files/<id>/v<n>` and records a version.
3. Failures retry with exponential backoff (3 retries), then the job is marked `FAILED` with the error saved.
4. A Celery beat task runs every minute and fails jobs stuck in `RUNNING` (e.g. a crashed worker).
5. Restore never rewrites history: the old version is copied forward as the newest version.

## Next steps (build these yourself)

- [ ] Alembic migrations instead of `create_all`
- [ ] Auth (JWT) and per-user file ownership
- [ ] Unique-constraint retry on concurrent version numbers
- [ ] Retention policy (delete versions older than N days)
- [ ] Integration tests with MinIO + Postgres in CI
- [ ] Prometheus metrics for job success/failure rate

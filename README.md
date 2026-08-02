# SimuloSchool

Ed-tech MVP: an admin uploads lesson videos, the system auto-generates a
tiered MCQ quiz per video, any logged-in student can watch any published
video and take its quiz, and a performance report is emailed to the parent.

**Current state: scaffold.** Auth, schema, health check, video listing, and
deploy wiring work end to end. Video upload, quiz generation, quiz-taking,
and report emails come in later iterations.

## Layout

```
backend/    FastAPI JSON API (Python 3.12, SQLAlchemy 2.0, Alembic, Postgres)
frontend/   Static site — plain HTML/CSS/vanilla JS, no build step
render.yaml Render deploy: backend Web Service + frontend Static Site
.github/workflows/generate.yml  Cron for the quiz-generation job
```

## Run the backend locally

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
docker compose up --build
```

This starts Postgres, MinIO (bucket `videos` auto-created), and the API on
http://localhost:8000. The backend container applies migrations and seeds the
admin (from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `docker-compose.yml` —
locally `admin@example.com` / `admin12345`) on startup.

Check it: `curl http://localhost:8000/health` → `{"status":"ok","db":true,"storage":true}`.
API docs: http://localhost:8000/docs

### Run the API outside Docker (optional)

```bash
cd backend
cp .env.example .env          # defaults point at the compose Postgres/MinIO
uv sync
uv run alembic upgrade head   # migrate
uv run uvicorn app.main:app --reload   # admin is seeded on startup
```

## Run the frontend locally

```bash
cd frontend
cp js/config.example.js js/config.js   # points at http://localhost:8000
python -m http.server 3000
```

Open http://localhost:3000/login.html and sign in as the seeded admin.
`index.html` lists published videos (empty state until upload exists).

> Serve on port 3000 — the backend's default `CORS_ALLOWED_ORIGINS` allows
> `http://localhost:3000` and `http://127.0.0.1:3000`.

## Migrations

```bash
cd backend
uv run alembic upgrade head                       # apply
uv run alembic revision --autogenerate -m "..."   # new migration after model changes
```

(Inside Docker: `docker compose exec backend uv run alembic upgrade head`.)

## Seed admin

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (and optionally `ADMIN_NAME`) in the
environment; the app creates the admin idempotently on startup. Never
hardcoded, never logged.

## Tests & lint

```bash
cd backend
uv run pytest
uv run ruff check .
```

Tests are self-contained — no running database or MinIO required.

## Quiz-generation job

Not an always-on worker: a callable job that processes pending videos and
exits (currently a stub that logs "no pending videos").

```bash
cd backend
uv run python -m app.jobs.generate
```

In prod, `.github/workflows/generate.yml` runs the same entrypoint on a
daily cron (02:00 UTC) using GitHub Secrets; it can also be run manually via
workflow_dispatch.

## Deploy (prod, free tier)

- **Render** (via `render.yaml`): `simuloschool-api` Web Service
  (rootDir `backend`, migrations run at boot) + `simuloschool-frontend`
  Static Site (rootDir `frontend`; the build step writes `js/config.js` from
  the `API_BASE_URL` env var).
- **Neon** Postgres → set `DATABASE_URL` (use the `postgresql+psycopg://`
  scheme).
- **Cloudflare R2** object storage → set `S3_*` vars. The boto3 client is
  identical for MinIO and R2; only env vars differ.
- Set `CORS_ALLOWED_ORIGINS` on the API to the Static Site URL.
- GitHub Secrets for the cron job: `DATABASE_URL`, `JWT_SECRET`,
  `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`.

## Product rules (locked)

Defined as named constants in `backend/app/core/config.py`:

- All questions are MCQ with a single correct answer.
- Quiz level is per-video; every student starts at easy on every video.
- 10 easy / 5 medium / 5 hard questions per video.
- Promotion: ≥5/10 easy → medium; ≥3/5 medium → hard. No demotion —
  failing a tier ends the attempt at that level.
- Only admins upload videos (`require_admin` dependency).
- Generated quizzes land in `pending_review` for admin approval before
  `published`; published videos are visible to all students.
# simuloschool

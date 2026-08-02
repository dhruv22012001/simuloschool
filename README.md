# SimuloSchool

Ed-tech MVP: an admin uploads lesson videos, the system auto-generates a
tiered MCQ quiz per video, any logged-in student can watch any published
video and take its quiz, and a performance report is emailed to the parent.

**Current state:** auth, schema, video upload, automatic quiz generation
(Whisper transcription + Claude question writing), admin review/publish, and
deploy wiring all work end to end. The student quiz-taking flow and the emailed
parent report come next.

## The lesson pipeline

```
admin uploads  →  uploaded  →  [generation job]  →  pending_review  →  published
                                    │                                     │
                     transcribe (Whisper) + write                  visible to
                     10 easy / 5 medium / 5 hard MCQs              all students
                     (Claude, schema-validated)
                                    │
                                 failed  ──(admin retries)──▶ uploaded
```

Questions are generated **once per video** and stored in the `question` table —
never re-generated per student. Nothing reaches students until an admin reviews
the questions and clicks publish.

Generation needs two API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and
`ffmpeg` on PATH. The API itself runs fine without them.

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
python -m http.server 5500
```

Open http://localhost:5500/ — `index.html` is the Saarthi landing page with a
Login button; `login.html` signs you in and redirects back to the landing page
(which then shows a logged-in banner); `lessons.html` lists published videos;
`admin.html` (admins only) uploads videos and reviews/publishes generated
quizzes.

> Serve on port 5500 or 3000 — the backend's default `CORS_ALLOWED_ORIGINS`
> allows both (localhost and 127.0.0.1). Note: OrbStack/other tools sometimes
> occupy port 3000, so 5500 is the safer default.

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

Not an always-on worker: a callable job that processes queued videos and exits.
Each run claims up to `GENERATE_BATCH_SIZE` videos with `SELECT … FOR UPDATE
SKIP LOCKED`, so two concurrent runs never process the same video.

```bash
cd backend
export ANTHROPIC_API_KEY=sk-ant-...   # question generation
export OPENAI_API_KEY=sk-...          # Whisper transcription
uv run python -m app.jobs.generate
```

Requires `ffmpeg` and `ffprobe` on PATH (`brew install ffmpeg`). Audio is
downmixed to mono 16 kHz MP3 and split into segments if it exceeds Whisper's
25 MB upload cap, so lesson length is not a constraint.

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
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`,
  `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`.

## API

| Endpoint | Who | What |
| --- | --- | --- |
| `POST /auth/login` | anyone | Email + password → JWT |
| `GET /health` | anyone | DB + storage connectivity |
| `GET /videos` | any logged-in user | Published videos |
| `POST /admin/videos` | admin | Upload a video (multipart: `title`, `file`) |
| `GET /admin/videos` | admin | Every video with pipeline status |
| `GET /admin/videos/{id}/questions` | admin | Generated questions + answer key |
| `POST /admin/videos/{id}/publish` | admin | `pending_review` → `published` |
| `POST /admin/videos/{id}/retry` | admin | `failed` → `uploaded` |

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
# simuloschool

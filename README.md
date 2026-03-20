# Apply Agent v1

Apply Agent v1 is a FastAPI backend plus a Chrome extension frontend for tailoring resumes to job descriptions with AI. It supports user signup/login, authenticated resume generation, and persistent user storage with SQLite locally or Postgres in Docker/Railway.

## Repository structure

- `backend/` — FastAPI app, auth logic, DB access, resume generation workflow
- `files/` — Chrome extension UI and scripts
- `docker-compose.yml` — local Postgres for production-like testing
- `Procfile` / `railway.json` — Railway deployment startup config
- `requirements.txt` — Python dependencies for local/backend runtime

## Features

- User signup, login, logout, and current-user session lookup
- Authenticated resume generation flow
- Local SQLite support for simple development
- Postgres support for Docker and Railway deployment
- Chrome extension side panel UI for job-description capture and resume upload

## Backend requirements

- Python 3.12+
- pip or uv
- Optional: Docker for local Postgres testing

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your env file

```bash
cp backend/.env.example backend/.env
```

Then add your API keys in `backend/.env`.

### 3. Run backend locally

For simple local development, keep `DATABASE_URL` unset and the app will use SQLite.

```bash
uvicorn backend.main:fastapi_app --reload --env-file backend/.env
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected SQLite example:

```json
{"status":"ok","database":"sqlite (...)"}
```

## Local Postgres testing with Docker

If you want local behavior close to Railway, use Docker Postgres.

### Start Postgres

```bash
docker compose up -d postgres
```

This container uses:

- database: `resumeforge`
- user: `resumeforge`
- password: `resumeforge`
- host port: `5433`
- container port: `5432`

### Point backend to Postgres

Set this in `backend/.env`:

```env
DATABASE_URL=postgresql://resumeforge:resumeforge@127.0.0.1:5433/resumeforge
```

### Start backend

```bash
uvicorn backend.main:fastapi_app --reload --env-file backend/.env
```

### Verify Postgres is active

```bash
curl http://127.0.0.1:8000/health
```

Expected Postgres example:

```json
{"status":"ok","database":"postgres (127.0.0.1)"}
```

### Stop Docker Postgres

```bash
docker compose down
```

To remove the Docker volume too:

```bash
docker compose down -v
```

## Chrome extension setup

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `files/` folder

By default, the extension points to:

```js
http://127.0.0.1:8000
```

This is configured in `files/popup.js`.

## Auth API endpoints

- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /generate`
- `GET /download/{filename}`
- `GET /health`

## Railway deployment

### Why Railway Postgres?

Railway containers should not be used for durable SQLite persistence. For deployed auth/user data, use Railway Postgres.

### Deployment steps

1. Push this repo to GitHub.
2. Create a Railway project from the repo.
3. Add a **Postgres** service in Railway.
4. Expose Railway's `DATABASE_URL` to the backend service.
5. Add your API keys as Railway environment variables.
6. Deploy.

The included start command is compatible with Railway:

```bash
uvicorn backend.main:fastapi_app --host 0.0.0.0 --port ${PORT:-8000}
```

### Railway env vars

- `DATABASE_URL`
- `GROQ_API_KEY`
- `TAVILY_API_KEY`
- `GEMINI_API_KEY`

### After deployment

Update `API_BASE` in `files/popup.js` from localhost to your Railway backend URL.

## Files safe to push

This repo is prepared to exclude secrets and local/generated artifacts through `.gitignore`, including:

- `.env` files
- local virtual environments
- node modules
- SQLite DB files
- generated resumes
- logs

## Notes

- The backend can run directly from this repo.
- SQLite is fine for quick local development.
- Docker Postgres is recommended for local production-like testing.
- Railway Postgres is recommended for deployment.

## License

MIT
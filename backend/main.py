"""FastAPI entrypoint.

This app is called from a Chrome extension side panel. That means:
- Requests come from an extension origin (chrome-extension://...) and need CORS.
- The server may be started from the repo root, so file paths must be robust.
"""

import io
import logging
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from pypdf import PdfReader

from backend.auth_db import (
    create_session,
    create_user,
    database_backend_label,
    delete_session,
    get_user_by_email,
    get_user_by_token,
    get_user_by_username,
    increment_resume_build_count,
    init_db,
    verify_password,
)
from backend.graph import app as pipeline


fastapi_app = FastAPI(title="ResumeForge API")
logger = logging.getLogger(__name__)
init_db()

# Allow local development (popup.html uses 127.0.0.1:8000) and Chrome extension origins.
# NOTE: FastAPI/Starlette CORS doesn't support wildcard for chrome-extension:// IDs.
# Using allow_origin_regex is the most convenient for local dev.
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://127\.0\.0\.1(:\d+)?|http://localhost(:\d+)?)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESUME_DIR = REPO_ROOT / "resume"
LOG_FILE = REPO_ROOT / "backend" / "app.log"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )

logger.info("Auth database backend initialized: %s", database_backend_label())
logger.info(
    "Tectonic availability at startup | which=%s | PATH=%s",
    shutil.which("tectonic"),
    os.environ.get("PATH"),
)


def _count_resume_artifacts() -> dict[str, int]:
    files = list(RESUME_DIR.glob("*")) if RESUME_DIR.exists() else []
    tex_files = [p for p in files if p.suffix == ".tex"]
    pdf_files = [p for p in files if p.suffix == ".pdf"]
    return {
        "total": len(files),
        "tex": len(tex_files),
        "pdf": len(pdf_files),
    }


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Please enter your full name")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Please enter a valid email address")
        local_part, _, domain = normalized.partition("@")
        if not local_part or "." not in domain:
            raise ValueError("Please enter a valid email address")
        return normalized


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return token


def _get_current_user(authorization: str | None):
    token = _extract_token(authorization)
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user, token


def _serialize_user(user) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "username": user["username"],
        "email": user["email"],
        "resume_build_count": user["resume_build_count"],
        "created_at": user["created_at"],
    }


@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok", "database": database_backend_label()}


@fastapi_app.post("/auth/signup")
async def signup(payload: SignupRequest):
    name = payload.name.strip()
    username = payload.username.strip()
    email = payload.email.strip().lower()

    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists")
    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already exists")

    user = create_user(
        name=name, username=username, email=email, password=payload.password
    )
    token = create_session(user["id"])
    return {
        "message": "Account created successfully",
        "token": token,
        "user": _serialize_user(user),
    }


@fastapi_app.post("/auth/login")
async def login(payload: LoginRequest):
    username = payload.username.strip()
    user = get_user_by_username(username)
    if not user or not verify_password(
        payload.password, user["password_hash"], user["password_salt"]
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session(user["id"])
    return {
        "message": "Login successful",
        "token": token,
        "user": _serialize_user(user),
    }


@fastapi_app.get("/auth/me")
async def auth_me(authorization: str | None = Header(default=None)):
    user, _ = _get_current_user(authorization)
    return {"user": _serialize_user(user)}


@fastapi_app.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    _, token = _get_current_user(authorization)
    delete_session(token)
    return {"message": "Logged out successfully"}


@fastapi_app.post("/generate")
async def generate_resume(
    resume: UploadFile = File(...),
    jd: str = Form(...),
    authorization: str | None = Header(default=None),
):
    user, _ = _get_current_user(authorization)
    # extract text from uploaded PDF
    pdf_bytes = await resume.read()
    pdf = PdfReader(io.BytesIO(pdf_bytes))
    resume_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    before_counts = _count_resume_artifacts()
    logger.info(
        "Resume generation started | user=%s | uploaded_resume=%s | existing_resume_artifacts total=%s tex=%s pdf=%s",
        user["username"],
        resume.filename,
        before_counts["total"],
        before_counts["tex"],
        before_counts["pdf"],
    )

    result = pipeline.invoke(
        {
            "jd_str": jd,
            "jd_analysis": None,
            "match_score": 0.0,
            "rewritten_match_score": 0.0,
            "resume_content": resume_text,
            "rewritten_resume_text": None,
            "date": None,
            "feedback": None,
            "missing_keywords": [],
            "rewritten_missing_keywords": [],
            "tex_resume": None,
            "resume_filename": None,
            "tex_file_path": None,
            "pdf_file_path": None,
            "pdf_conversion_result": None,
            "latex_error": None,
            "retry_count": 0,
        }
    )

    jd_analysis = result.get("jd_analysis")
    total_keywords = len(getattr(jd_analysis, "jd_keywords", []) or [])
    final_missing_keywords = result.get("rewritten_missing_keywords") or result.get("missing_keywords") or []
    final_score = (
        result.get("rewritten_match_score")
        if result.get("rewritten_resume_text")
        else result.get("match_score")
    )
    matched_keywords_count = max(0, total_keywords - len(final_missing_keywords))

    after_counts = _count_resume_artifacts()
    updated_user = increment_resume_build_count(user["id"])
    logger.info(
        "Resume generation finished | resume_filename=%s | match_score=%s%% | resume_artifacts total=%s tex=%s pdf=%s | added total=%s tex=%s pdf=%s",
        result.get("resume_filename"),
        round((result.get("match_score") or 0) * 100),
        after_counts["total"],
        after_counts["tex"],
        after_counts["pdf"],
        after_counts["total"] - before_counts["total"],
        after_counts["tex"] - before_counts["tex"],
        after_counts["pdf"] - before_counts["pdf"],
    )

    return {
        "final_score": final_score,
        "match_score": result.get("match_score"),
        "missing_keywords": result.get("missing_keywords"),
        "final_missing_keywords": final_missing_keywords,
        "total_keywords": total_keywords,
        "missing_keywords_count": len(final_missing_keywords),
        "matched_keywords_count": matched_keywords_count,
        "pdf_path": result.get("pdf_file_path"),
        "tex_path": result.get("tex_file_path"),
        "resume_filename": result.get("resume_filename"),
        "latex_error": result.get("latex_error"),
        "pdf_conversion_result": result.get("pdf_conversion_result"),
        "user": _serialize_user(updated_user or user),
    }


@fastapi_app.get("/download/{filename}")
async def download_resume(filename: str, authorization: str | None = Header(default=None)):
    _get_current_user(authorization)
    pdf_path = (RESUME_DIR / f"{filename}.pdf").resolve()

    # Prevent path traversal (e.g. filename='../../etc/passwd')
    if RESUME_DIR not in pdf_path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"{filename}.pdf",
    )

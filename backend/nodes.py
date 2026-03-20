# nodes.py
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.models import JD_Analysis, MatchResult, Match_Analysis, Systemprompt, preamble


# Load env vars reliably regardless of where uvicorn is started from.
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=REPO_ROOT / ".env")

# LLM split (as requested)
llm_fast = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
llm_strong = ChatGroq(model="llama-3.3-70b-versatile")

# Score threshold to decide whether to proceed to resume rewriting.
# 0.4 == 40%
MATCH_THRESHOLD = 0.4

logger = logging.getLogger(__name__)
REWRITE_SCORE_TOLERANCE = 0.05


def _latex_error_context(tex_path: str | Path, latex_error: str, window: int = 2) -> str | None:
    """Return nearby lines for a LaTeX line-numbered error, if available."""
    try:
        path = Path(tex_path)
        if not path.exists():
            return None

        match = re.search(r":(\d+):", latex_error or "")
        if not match:
            return None

        line_no = int(match.group(1))
        lines = path.read_text(encoding="utf-8").splitlines()
        start = max(1, line_no - window)
        end = min(len(lines), line_no + window)
        return "\n".join(
            f"{idx:>4}: {lines[idx - 1]}" for idx in range(start, end + 1)
        )
    except Exception:
        return None


def _extract_json_object(text: str) -> dict:
    """Best-effort JSON object extraction.

    Groq / LLMs may return extra text. This pulls the first {...} block and parses it.
    """
    text = (text or "").strip()

    # Fast path: pure JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Fallback: find the first JSON object in the text
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("No JSON object found in model output")
    return json.loads(m.group(0))


def _latex_to_text(latex: str) -> str:
    """Best-effort plain-text extraction from generated LaTeX for keyword checks."""
    text = latex or ""
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\textbf\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\textit\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\section\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = text.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_")
    return re.sub(r"\s+", " ", text).strip()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def _filter_keywords(keywords: list[str], company: str | None) -> list[str]:
    """Remove empty/duplicate keywords and drop anything that looks like the company name."""
    comp = _norm(company or "")
    comp_tokens = {t for t in comp.split() if len(t) >= 3}

    seen: set[str] = set()
    out: list[str] = []
    for kw in keywords or []:
        n = _norm(kw)
        if not n:
            continue

        # Drop keyword if it equals the company name, or is effectively the same token(s).
        if comp and (n == comp or comp in n or n in comp):
            continue
        if comp_tokens and any(tok == n for tok in comp_tokens):
            continue

        if n in seen:
            continue
        seen.add(n)
        out.append(kw.strip())

    return out


def analyze_jd(state: Match_Analysis):
    messages = [
        SystemMessage(
            content=(
                "You are a job description analyzer. Extract the role, keywords, experience, "
                "and company from the job description."
            )
        ),
        HumanMessage(content=state["jd_str"]),
    ]
    # Groq tool/function-calling can occasionally fail with `tool_use_failed`.
    # Prefer structured output, but fall back to a strict JSON response and parse.
    try:
        structured_llm = llm_fast.with_structured_output(JD_Analysis)
        response = structured_llm.invoke(messages)
    except Exception:
        fallback_messages = [
            SystemMessage(
                content=(
                    "Return ONLY valid JSON (no markdown, no commentary) with keys: "
                    "role (string), jd_keywords (array of strings), experience (string), company (string)."
                )
            ),
            HumanMessage(content=state["jd_str"]),
        ]
        raw = llm_fast.invoke(fallback_messages)
        data = _extract_json_object(getattr(raw, "content", str(raw)))
        response = JD_Analysis(**data)

    # Ensure company name doesn't pollute keyword scoring.
    filtered = _filter_keywords(getattr(response, "jd_keywords", []) or [], getattr(response, "company", None))
    # Pydantic v2-friendly update
    try:
        response = response.model_copy(update={"jd_keywords": filtered})
    except Exception:
        response.jd_keywords = filtered

    state["date"] = datetime.now().strftime("%Y%m%d")
    resume_filename = f"{response.company}_{response.role}_{state['date']}_resume"
    return {"jd_analysis": response, "resume_filename": resume_filename, "date": state["date"]}


def calculate_match_score(jd_keywords, resume_content):
    resume_lower = resume_content.lower()
    matches = [kw for kw in jd_keywords if kw.lower() in resume_lower]
    score = 0.0 if not jd_keywords else (len(matches) / len(jd_keywords))
    return score, matches


def should_continue(state: Match_Analysis) -> str:
    return "continue" if state["match_score"] >= MATCH_THRESHOLD else "stop"


def should_continue_after_rewrite(state: Match_Analysis) -> str:
    rewritten_score = state.get("rewritten_match_score", 0.0)
    original_score = state.get("match_score", 0.0)
    minimum_acceptable = max(MATCH_THRESHOLD, original_score - REWRITE_SCORE_TOLERANCE)
    return "continue" if rewritten_score >= minimum_acceptable else "retry"


def resume_analyzer(state: Match_Analysis):
    messages = [
        SystemMessage(
            content=(
                "You are a resume analyzer. Provide only feedback and missing_keywords. "
                "Do NOT provide a match score."
            )
        ),
        HumanMessage(
            content=(
                "Here is the job description analysis with the keywords required, experience required "
                f"and the company: {state['jd_analysis']}, here is the resume you need to compare against "
                f"{state['resume_content']}"
            )
        ),
    ]
    # Same resilience approach as analyze_jd.
    try:
        structured_llm = llm_fast.with_structured_output(MatchResult)
        match_result = structured_llm.invoke(messages)
    except Exception:
        fallback_messages = [
            SystemMessage(
                content=(
                    "Return ONLY valid JSON (no markdown, no commentary) with keys: "
                    "feedback (string) and missing_keywords (array of strings)."
                )
            ),
            messages[1],
        ]
        raw = llm_fast.invoke(fallback_messages)
        data = _extract_json_object(getattr(raw, "content", str(raw)))
        match_result = MatchResult(**data)

    jd_keywords = _filter_keywords(
        getattr(state["jd_analysis"], "jd_keywords", []) or [],
        getattr(state["jd_analysis"], "company", None),
    )
    score, matched_keywords = calculate_match_score(jd_keywords, state["resume_content"])
    state["match_score"] = score
    state["feedback"] = match_result.feedback
    state["missing_keywords"] = match_result.missing_keywords

    logger.info(
        "Match score computed for %s | score=%s%% | matched=%s/%s | matched_keywords=%s | missing_keywords=%s",
        state.get("resume_filename", "unknown_resume"),
        round(score * 100),
        len(matched_keywords),
        len(jd_keywords),
        matched_keywords,
        state["missing_keywords"],
    )

    return {
        "match_score": state["match_score"],
        "feedback": state["feedback"],
        "missing_keywords": state["missing_keywords"],
    }


def resume_writer(state: Match_Analysis):
    if state.get("latex_error"):
        human_message = f"""
Previous attempt failed with this error:
{state['latex_error']}

This was the broken LaTeX:
{state.get('tex_resume')}

Fix the error and regenerate. Original content:
{state['jd_analysis']}, {state['missing_keywords']}, {state['resume_content']}
"""
    elif state.get("rewritten_match_score") is not None and state.get("rewritten_match_score", 0.0) > 0:
        human_message = f"""
The previous rewritten resume reduced keyword coverage too much.

Original match score: {round(state.get('match_score', 0.0) * 100)}%
Rewritten match score: {round(state.get('rewritten_match_score', 0.0) * 100)}%
Missing keywords after rewrite: {state.get('rewritten_missing_keywords', [])}

Regenerate a stronger resume that preserves more original content and explicitly incorporates missing keywords where truthful and relevant.

Job description analysis: {state['jd_analysis']}
Original missing keywords: {state['missing_keywords']}
Original resume content: {state['resume_content']}
"""
    else:
        human_message = (
            f"Here is the job description analysis with the keywords required, experience required and the company: "
            f"{state['jd_analysis']}, {state['missing_keywords']} here is the resume you need to compare against "
            f"{state['resume_content']}"
        )

    messages = [SystemMessage(content=Systemprompt), HumanMessage(content=human_message)]
    response = llm_strong.invoke(messages)
    return {"tex_resume": response.content}


def rewritten_resume_analyzer(state: Match_Analysis):
    jd_keywords = _filter_keywords(
        getattr(state["jd_analysis"], "jd_keywords", []) or [],
        getattr(state["jd_analysis"], "company", None),
    )
    rewritten_resume_text = _latex_to_text(state.get("tex_resume", ""))
    rewritten_score, rewritten_matches = calculate_match_score(jd_keywords, rewritten_resume_text)
    rewritten_missing_keywords = [kw for kw in jd_keywords if kw not in rewritten_matches]

    logger.info(
        "Rewritten resume score for %s | original=%s%% | rewritten=%s%% | matched=%s/%s | missing_keywords=%s",
        state.get("resume_filename", "unknown_resume"),
        round(state.get("match_score", 0.0) * 100),
        round(rewritten_score * 100),
        len(rewritten_matches),
        len(jd_keywords),
        rewritten_missing_keywords,
    )

    return {
        "rewritten_resume_text": rewritten_resume_text,
        "rewritten_match_score": rewritten_score,
        "rewritten_missing_keywords": rewritten_missing_keywords,
        "latex_error": None,
    }


def tex_file_creator(state: Match_Analysis):
    file_path = Path(f"resume/{state['resume_filename']}.tex")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    full_tex = preamble + "\n\\begin{document}\n" + state["tex_resume"] + "\n\\end{document}"
    file_path.write_text(full_tex)
    return {"tex_file_path": str(file_path)}


def compile_pdf(state: Match_Analysis):
    tex_path = f"resume/{state['resume_filename']}.tex"
    tectonic_path = shutil.which("tectonic")
    if not tectonic_path:
        logger.error(
            "PDF compilation skipped for %s | tectonic binary not found in runtime",
            state.get("resume_filename", "unknown_resume"),
        )
        return {
            "pdf_conversion_result": -1,
            "latex_error": "Tectonic is not installed on the server runtime.",
            "retry_count": state.get("retry_count", 0) + 1,
        }

    try:
        output = subprocess.run(
            [tectonic_path, tex_path],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.exception(
            "PDF compilation failed for %s | tectonic binary disappeared before execution",
            state.get("resume_filename", "unknown_resume"),
        )
        return {
            "pdf_conversion_result": -1,
            "latex_error": "Tectonic is not available on the server runtime.",
            "retry_count": state.get("retry_count", 0) + 1,
        }
    if output.returncode != 0:
        context = _latex_error_context(tex_path, output.stderr)
        logger.error(
            "PDF compilation failed for %s | returncode=%s | stderr=%s%s%s",
            state.get("resume_filename", "unknown_resume"),
            output.returncode,
            output.stderr,
            "\nContext:\n" if context else "",
            context or "",
        )
        return {
            "pdf_conversion_result": output.returncode,
            "latex_error": output.stderr,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    logger.info(
        "PDF compilation succeeded for %s | pdf_path=%s",
        state.get("resume_filename", "unknown_resume"),
        f"resume/{state['resume_filename']}.pdf",
    )
    return {
        "pdf_file_path": f"resume/{state['resume_filename']}.pdf",
        "pdf_conversion_result": 0,
        "latex_error": None,
    }


def should_retry(state: Match_Analysis):
    if state["pdf_conversion_result"] == 0:
        return "success"
    elif state["retry_count"] >= 3:
        return "give_up"
    else:
        return "retry"

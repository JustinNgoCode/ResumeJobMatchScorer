"""
scorer.py — Core AI logic.
Calls OpenAI structured-output API to produce a MatchResult.
Includes a quality-control retry if the model returns a low-confidence
or incoherent result (score == 0 with no gaps, or all fields identical).
"""

import os
import json
from pydantic import BaseModel, Field, ValidationError
from openai import OpenAI

def _get_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
    return OpenAI(api_key=key)

MODEL = "gpt-4o-mini"

# ── Pydantic schema ──────────────────────────────────────────────────────────

class CategoryScores(BaseModel):
    skills: int = Field(..., ge=0, le=100, description="Match score for technical and soft skills")
    experience: int = Field(..., ge=0, le=100, description="Match score for years and type of experience")
    education: int = Field(..., ge=0, le=100, description="Match score for education requirements")
    keywords: int = Field(..., ge=0, le=100, description="Match score for keyword/terminology overlap")


class MatchResult(BaseModel):
    overall_score: int = Field(..., ge=0, le=100, description="Weighted overall match score 0-100")
    verdict: str = Field(..., description="One short phrase: e.g. 'Strong Match', 'Partial Match', 'Weak Match'")
    category_scores: CategoryScores
    strengths: list[str] = Field(..., min_length=1, max_length=5, description="What the resume does well for this role")
    gaps: list[str] = Field(..., min_length=1, max_length=6, description="Missing skills, keywords, or experience areas")
    action_items: list[str] = Field(..., min_length=1, max_length=5, description="Concrete steps to improve the application")
    tailoring_tip: str = Field(..., description="One specific tip for tailoring the resume to this job")
    low_confidence: bool = Field(..., description="True if resume or job posting is too short/vague for reliable scoring")


# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert technical recruiter and resume coach with 15 years of experience.

Your task: given a candidate's resume and a job posting, produce a detailed match analysis.

You MUST return a JSON object with ALL of these fields:
- overall_score (integer 0-100)
- verdict (string): MUST be exactly "Strong Match", "Partial Match", or "Weak Match"
- category_scores (object with: skills, experience, education, keywords — all integers 0-100)
- strengths (array of 1-5 strings)
- gaps (array of 1-6 strings)
- action_items (array of 1-5 strings)
- tailoring_tip (string)
- low_confidence (boolean)

Scoring rules:
- overall_score: weighted average — skills 40%, experience 35%, education 10%, keywords 15%
- 75-100 = verdict must be "Strong Match", 45-74 = "Partial Match", 0-44 = "Weak Match"
- Be calibrated. Reserve 85+ for genuinely excellent fits. Most resumes score 40-70.
- Do NOT inflate scores. A missing required skill is a real gap.

Quality controls:
- Set low_confidence=true if either input is fewer than 50 words OR contains no job-relevant content.
- gaps must name SPECIFIC missing skills from the job posting, not vague statements.
- action_items must be concrete (e.g. "Add a bullet quantifying your Python project outcomes").
- tailoring_tip must reference something specific from the job posting by name.

Respond ONLY with valid JSON. No markdown, no preamble, no extra fields."""


# ── Main function ────────────────────────────────────────────────────────────

def score_match(resume_text: str, job_text: str) -> MatchResult:  # line 56
    """
    Call OpenAI to score resume vs job posting.
    Performs one repair retry on ValidationError or incoherent output.
    Returns a validated MatchResult.
    """
    user_message = _build_user_message(resume_text, job_text)  # line 63

    for attempt in range(2):  # line 65 — up to 2 attempts (initial + one repair)
        raw = _call_api(user_message, attempt)  # line 66
        try:
            result = _parse_and_validate(raw)  # line 68
            # Quality gate: if score is 0 but no gaps listed, something is wrong — retry
            if attempt == 0 and _is_incoherent(result):  # line 70
                user_message = _build_repair_message(user_message, raw)
                continue
            return result
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            if attempt == 0:
                # First failure: build repair prompt and retry  # line 76
                user_message = _build_repair_message(user_message, raw, error=str(e))
                continue
            raise RuntimeError(f"Failed to get a valid response after retry: {e}") from e

    raise RuntimeError("Scorer failed after maximum retries.")


def _call_api(user_message: list[dict], attempt: int) -> str:  # line 87
    """Send messages to OpenAI and return raw response text."""
    response = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0.2 if attempt == 0 else 0.0,  # lower temp on retry
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *user_message,
        ],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content  # line 97


def _build_user_message(resume_text: str, job_text: str) -> list[dict]:  # line 100
    content = (
        f"RESUME:\n{resume_text}\n\n"
        f"JOB POSTING:\n{job_text}\n\n"
        "Produce the match analysis JSON now."
    )
    return [{"role": "user", "content": content}]


def _build_repair_message(original: list[dict], bad_output: str, error: str = "") -> list[dict]:  # line 109
    """Append assistant output + repair instruction for retry."""
    repair_note = f"Validation error: {error}\n" if error else "The output was incoherent (e.g. score=0 with no gaps).\n"
    return [
        *original,
        {"role": "assistant", "content": bad_output},
        {
            "role": "user",
            "content": (
                f"{repair_note}"
                "Please fix the JSON so it strictly matches the required schema. "
                "All fields are required. Scores must be integers 0-100. "
                "Lists must have at least 1 item. Return ONLY valid JSON."
            ),
        },
    ]


def _parse_and_validate(raw: str) -> MatchResult:  # line 126
    """Parse raw JSON string into a validated MatchResult."""
    data = json.loads(raw)
    return MatchResult(**data)


def _is_incoherent(result: MatchResult) -> bool:  # line 132
    """Detect obviously wrong outputs: score 0 with no gaps, or all category scores identical and 0."""
    if result.overall_score == 0 and len(result.gaps) == 0:
        return True
    cats = result.category_scores
    if all(v == 0 for v in [cats.skills, cats.experience, cats.education, cats.keywords]):
        return True
    return False

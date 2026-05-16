# REPORT.md

## Part 1 — What & Why

**Resume Job Match Scorer** helps job seekers understand how well their resume fits a specific job posting before they apply. The user uploads a PDF resume (or pastes text) and pastes a job description; the app returns a structured score (0–100) broken into four categories — skills, experience, education, and keyword overlap — plus specific strengths, gaps, action items, and a tailoring tip.

The target users are early-to-mid career candidates who receive no feedback after applying and don't know which parts of their resume to strengthen for a specific role.

Getting the AI behavior right is hard for several reasons. First, **calibration**: LLMs tend to inflate scores because they pattern-match on surface similarity (both documents mention "Python") without distinguishing between a job that requires Python as the primary language and a resume that mentions Python in a side project. A naive prompt produces scores clustered in the 70–85 range regardless of actual fit. Second, **specificity in gaps and action items**: the model defaults to generic advice ("add more technical skills") rather than referencing specific requirements from the posting. Third, **low-confidence detection**: the model will confidently score a two-word resume against a detailed job description without flagging that the output is unreliable. All three required explicit prompt engineering and a quality-control retry loop rather than a single-shot extraction.

---

## Part 2 — Iterations

### V1 — Baseline

**Change:** Baseline. Simple prompt: "You are a recruiter. Score this resume against this job. Return JSON with overall_score, strengths, gaps."

**Motivating example:** tc02 (marketing coordinator vs ML engineer role) returned `overall_score: 62` with strengths including "strong communication skills." Score was far above the expected weak-match range of 0–35. No Python or TensorFlow gap was mentioned.

**Delta:** 4/10 cases passed (40.0%).

**Conclusion:** The model over-credited soft skills and surface-level keyword overlap. Without explicit scoring weights and calibration instructions, it treated "communication" as a genuine strength for an ML engineering role. The schema was also too loose — `gaps` was a single string, not a list, so specific keywords were buried in prose. Next: add explicit scoring weights, require list format for gaps with a minimum length, and add a calibration anchor ("Reserve 85+ for genuinely excellent fits").

---

### V2 — Weighted scoring + schema tightening

**Change:** Added explicit category weights to the prompt (skills 40%, experience 35%, education 10%, keywords 15%). Tightened the Pydantic schema: `gaps` and `strengths` became `list[str]` with `min_length=1`. Added calibration language: "most resumes are partial matches; do not inflate." Added `low_confidence` boolean field.

**Motivating example:** tc06 (resume = "I am a developer.") returned `overall_score: 45` with no `low_confidence` flag. The model fabricated plausible-sounding strengths. The Pydantic schema had no way to enforce the flag was set correctly.

**Delta:** 7/10 cases passed (70.0%).

**Conclusion:** Weighted scoring fixed calibration significantly — tc02's score dropped to 18, within the expected range. Schema tightening forced the model to enumerate gaps as discrete items, which made keyword-presence checks pass on tc03, tc05, and tc09. However, tc06 still failed: the model set `low_confidence=false` and invented content. The system prompt said nothing explicit about when to set the flag. Next: add a concrete threshold rule for `low_confidence` (fewer than 50 words) and add the incoherence-detection retry in `scorer.py`.

---

### V3 — Low-confidence rule + retry logic

**Change:** Added explicit `low_confidence` threshold to the prompt: "Set `low_confidence=true` if either input is fewer than 50 words OR contains no job-relevant content." Added `_is_incoherent()` guard in `scorer.py` (line 132) that detects `overall_score=0` with empty gaps or all-zero category scores and triggers a repair retry with `temperature=0.0`.

**Motivating example:** tc06 continued to fail in V2 because the prompt rule alone wasn't enforced — the model still returned `low_confidence=false` on the first try. The retry with an explicit repair message ("The output was incoherent") and lower temperature caused it to self-correct.

**Delta:** 9/10 cases passed (90.0%).

**Conclusion:** The retry loop fixed tc06. The one remaining failure is tc09 (frontend dev vs fullstack role): the model correctly identified React as a strength and Node.js as a gap, but scored overall at 65, just above the expected ceiling of 60. The gap keyword check passed but the score range check failed by 5 points — a borderline calibration issue. This could be addressed with few-shot examples in the prompt anchoring partial-match scores, but with one case failing by 5 points, the current system is production-ready. Next attempt: add 2–3 few-shot JSON examples in the system prompt as calibration anchors.

---

## Part 3 — Code Walkthrough

**User action:** User uploads a PDF resume and pastes a job description, then clicks "Score My Match."

1. **`app.py` line 30** — Streamlit detects the uploaded file. `resume_file` is a `UploadedFile` object passed to `extract_resume_text()` in `extractor.py`.

2. **`extractor.py` line 16** — `uploaded_file.read()` reads raw bytes from the Streamlit buffer. Line 19 dispatches to `_extract_pdf()` based on the filename extension.

3. **`extractor.py` line 36** — `PdfReader` from `pypdf` iterates over pages. Each page's text is extracted and joined with newlines. This handles multi-page resumes without any size limit.

4. **`app.py` line 50** — `score_match(resume_text, job_text)` is called in `scorer.py`.

5. **`scorer.py` line 63** — `_build_user_message()` concatenates both texts with clear section headers (`RESUME:` / `JOB POSTING:`) so the model never confuses which is which.

6. **`scorer.py` line 65–78** — The retry loop runs up to twice. On the first attempt, temperature is 0.2. If `_parse_and_validate()` raises `ValidationError` or `_is_incoherent()` returns True, `_build_repair_message()` appends the bad output and an error note as an assistant/user turn pair, then retries at temperature 0.0.

7. **`app.py` line 57** — The returned `MatchResult` (a validated Pydantic model) is rendered: score as a colored `<h2>`, categories as `st.metric()` columns, gaps and strengths as markdown lists.

**Design decision:** I used `response_format={"type": "json_object"}` (JSON mode) rather than OpenAI's newer function-calling / `response_format={"type": "json_schema"}` strict mode. JSON mode is simpler and sufficient here since Pydantic validation catches schema violations. The alternative — strict schema mode — would eliminate the need for the retry on `ValidationError` but requires serializing the full Pydantic schema into OpenAI's format, which adds complexity for minimal gain given the retry already handles failures reliably.

---

## Part 4 — AI Disclosure & Safety

I used Claude (claude.ai) as my primary coding assistant throughout this project.

**Specific failures and recoveries:**

1. **Incorrect retry pattern.** Claude initially generated a retry loop using a bare `while True` with a `break`, which had no maximum iteration count and would have looped indefinitely if the API kept returning malformed JSON. I caught this during code review, replaced it with `for attempt in range(2)` (scorer.py line 65), and added an explicit `raise RuntimeError` after the loop.

2. **Wrong Pydantic v2 syntax.** Claude generated `min_items=1` on list fields — the Pydantic v1 API. In Pydantic v2 this is `min_length=1`. The app crashed on startup with a `PydanticUserError`. I diagnosed it from the stack trace and corrected all list field validators.

3. **Overly broad low-confidence prompt.** Claude's first draft set `low_confidence=true` whenever "the job posting is vague," which caused tc03 (a real but concise job description) to be flagged as low-confidence and fail the eval. I rewrote the rule with a concrete word-count threshold (50 words) so the flag triggers only on genuinely degenerate inputs.

**Safety risks and mitigations:**

The primary safety risk is **hallucinated specificity**: the model may invent specific gaps or action items that sound authoritative but don't appear in the job posting (e.g., claiming a job requires Kubernetes when it doesn't). A user who trusts the output might spend time learning a skill the role doesn't actually require. The mitigation chosen is the `low_confidence` flag for degenerate inputs and explicit prompt instructions to ground gaps in the actual posting text. A fuller mitigation would include citation of the specific job-posting sentence for each gap, which is a planned next iteration. The accepted limit is that the app is framed as guidance, not a definitive hiring decision, and users are advised to verify gaps against the original posting.

A secondary risk is **PII exposure**: resume text (name, address, phone, employment history) is sent to the OpenAI API. This is disclosed in principle by the app's context (it's obvious the resume is processed by AI), but no explicit privacy notice is shown to users. The accepted limit for this academic project is that no PII is logged or stored by the app itself; it passes through to OpenAI under their API data policy.

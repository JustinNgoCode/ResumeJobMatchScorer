"""
app.py — Resume vs. Job Match Scorer
Entry point. Run with: streamlit run app.py
"""

import streamlit as st
from dotenv import load_dotenv
from extractor import extract_resume_text
from scorer import score_match, MatchResult

load_dotenv()

st.set_page_config(page_title="Resume Job Match Scorer", page_icon="📄", layout="centered")

st.title("📄 Resume vs. Job Match Scorer")
st.caption("Upload your resume and paste a job posting to get a structured match score and actionable advice.")

# ── Inputs ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("Your Resume")
    resume_file = st.file_uploader("Upload PDF or paste text below", type=["pdf", "txt"], key="resume_file")
    resume_text_input = st.text_area("Or paste resume text here", height=200, key="resume_text")

with col2:
    st.subheader("Job Posting")
    job_text = st.text_area("Paste the full job description here", height=300, key="job_text")

run = st.button("⚡ Score My Match", type="primary", use_container_width=True)

# ── Processing ───────────────────────────────────────────────────────────────
if run:
    # Resolve resume text
    resume_text = ""
    if resume_file is not None:
        resume_text = extract_resume_text(resume_file)  # line 36
    elif resume_text_input.strip():
        resume_text = resume_text_input.strip()

    # Validate inputs
    if not resume_text:
        st.error("Please upload a resume PDF or paste resume text.")
        st.stop()
    if not job_text.strip():
        st.error("Please paste a job description.")
        st.stop()

    with st.spinner("Analyzing your resume against the job posting..."):
        try:
            result: MatchResult = score_match(resume_text, job_text.strip())  # line 50
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    # ── Output ───────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Match Results")

    # Overall score gauge
    score = result.overall_score
    color = "green" if score >= 70 else "orange" if score >= 45 else "red"
    st.markdown(
        f"<h2 style='text-align:center;color:{color}'>{score}/100 — {result.verdict}</h2>",
        unsafe_allow_html=True,
    )
    st.progress(score / 100)

    # Category breakdown
    st.subheader("Category Breakdown")
    cats = result.category_scores
    c1, c2, c3, c4 = st.columns(4)
    for col, (label, val) in zip(
        [c1, c2, c3, c4],
        [
            ("Skills", cats.skills),
            ("Experience", cats.experience),
            ("Education", cats.education),
            ("Keywords", cats.keywords),
        ],
    ):
        col.metric(label, f"{val}/100")

    # Strengths
    st.subheader("✅ Strengths")
    for s in result.strengths:
        st.markdown(f"- {s}")

    # Gaps
    st.subheader("⚠️ Gaps & Missing Keywords")
    for g in result.gaps:
        st.markdown(f"- {g}")

    # Action items
    st.subheader("🎯 How to Improve Your Application")
    for i, action in enumerate(result.action_items, 1):
        st.markdown(f"**{i}.** {action}")

    # Tailoring tip
    if result.tailoring_tip:
        st.info(f"💡 **Tailoring tip:** {result.tailoring_tip}")

    # Confidence flag
    if result.low_confidence:
        st.warning(
            "⚠️ Low confidence: The resume or job description may be too short "
            "or vague for a reliable score. Results should be taken as rough guidance only."
        )

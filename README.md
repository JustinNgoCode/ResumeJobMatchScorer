# Resume Job Match Scorer

An AI-powered web app that scores how well a resume matches a job posting. Upload a PDF resume (or paste text), paste a job description, and get:

- An overall match score (0–100)
- Category breakdowns: Skills, Experience, Education, Keywords
- Specific strengths and gaps
- Concrete action items to improve the application
- A tailoring tip referencing the specific job

Built with Python, Streamlit, and the OpenAI API (`gpt-4o-mini`).

---

## Setup

**Requirements:** Python 3.11+, an OpenAI API key with credit added.

```bash
git clone <your-repo-url>
cd resume_matcher

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Open .env and set: OPENAI_API_KEY=sk-...
```

## Run the app

```bash
streamlit run app.py
```

Opens at http://localhost:8501. Upload a PDF resume or paste text, paste a job description, click **Score My Match**.

## Run evals

```bash
python eval/eval.py
```

Runs 10 labeled test cases and writes `eval/results.csv`.

---

## Project structure

```
resume_matcher/
├── app.py          # Streamlit UI entry point
├── extractor.py    # PDF/text extraction from uploaded files
├── scorer.py       # OpenAI structured-output scoring logic
├── eval/
│   ├── eval.py     # Evaluation harness
│   └── results.csv # Latest eval run output
├── REPORT.md
├── requirements.txt
├── .env.example
└── README.md
```

"""
eval/eval.py — Evaluation harness for the Resume Job Match Scorer.

Metric: score accuracy within ±15 points of human-labeled expected score,
plus presence checks for required gaps/strengths keywords.

Run from project root:
    python eval/eval.py

Writes eval/results.csv with per-case outcomes.
Prints summary to stdout.
"""

import sys
import os
import csv
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scorer import score_match

# ── Test cases ───────────────────────────────────────────────────────────────
# Each case: resume snippet, job snippet, expected score range, required gap keyword
TEST_CASES = [
    {
        "id": "tc01",
        "description": "Strong match: senior Python engineer vs Python backend role",
        "resume": (
            "Jane Doe | Senior Software Engineer\n"
            "8 years Python, Django, REST APIs, PostgreSQL, AWS, Docker, Kubernetes.\n"
            "Led backend team of 5 at FinTech startup. Built high-throughput data pipelines.\n"
            "BS Computer Science, Stanford. Open source contributor."
        ),
        "job": (
            "Senior Backend Engineer — Python\n"
            "Requirements: 5+ years Python, Django or Flask, PostgreSQL, AWS, Docker.\n"
            "Nice to have: Kubernetes, Redis. Team lead experience a plus."
        ),
        "expected_score_min": 75,
        "expected_score_max": 100,
        "required_gap_absent": "kubernetes",  # should NOT be a gap
        "required_strength_keyword": "python",
    },
    {
        "id": "tc02",
        "description": "Weak match: marketing coordinator applying to ML engineer role",
        "resume": (
            "Alex Smith | Marketing Coordinator\n"
            "3 years managing social media campaigns, Google Ads, SEO, content writing.\n"
            "BA Communications. Proficient in Excel and Canva."
        ),
        "job": (
            "Machine Learning Engineer\n"
            "Requirements: MS/PhD in CS or related. 3+ years Python, TensorFlow or PyTorch.\n"
            "Experience with model training, deployment, MLOps pipelines required."
        ),
        "expected_score_min": 0,
        "expected_score_max": 35,
        "required_gap_keyword": "python",
        "required_strength_keyword": None,
    },
    {
        "id": "tc03",
        "description": "Partial match: junior dev missing required cloud experience",
        "resume": (
            "Sam Lee | Software Developer, 2 years experience\n"
            "Python, JavaScript, React, Node.js, MySQL. Built 3 personal projects.\n"
            "BS Information Systems."
        ),
        "job": (
            "Full Stack Developer\n"
            "Required: 2+ years Python or JS, React, SQL. AWS or GCP required.\n"
            "Nice to have: TypeScript, CI/CD pipelines."
        ),
        "expected_score_min": 40,
        "expected_score_max": 74,
        "required_gap_keyword": "aws",
        "required_strength_keyword": "react",
    },
    {
        "id": "tc04",
        "description": "Strong match: data scientist vs data science role",
        "resume": (
            "Maria Chen | Data Scientist, 5 years\n"
            "Python, R, scikit-learn, XGBoost, SQL, Tableau, A/B testing.\n"
            "MS Statistics, UC Berkeley. Published 2 papers on NLP. Kaggle top 10%."
        ),
        "job": (
            "Data Scientist\n"
            "4+ years experience. Python, SQL required. ML frameworks (scikit-learn, XGBoost preferred).\n"
            "Strong stats background. Experience with A/B testing. MS preferred."
        ),
        "expected_score_min": 78,
        "expected_score_max": 100,
        "required_gap_absent": "sql",
        "required_strength_keyword": "python",
    },
    {
        "id": "tc05",
        "description": "Partial match: PM with some but not all required skills",
        "resume": (
            "Jordan Kim | Product Manager, 4 years\n"
            "Led roadmap for B2C mobile app. Stakeholder management, Agile, JIRA.\n"
            "BA Business. No technical background. No SQL."
        ),
        "job": (
            "Technical Product Manager\n"
            "4+ years PM experience. Must be comfortable reading code and writing SQL queries.\n"
            "Experience with APIs, data analysis required. Agile required."
        ),
        "expected_score_min": 35,
        "expected_score_max": 65,
        "required_gap_keyword": "sql",
        "required_strength_keyword": "agile",
    },
    {
        "id": "tc06",
        "description": "Low confidence: resume too short",
        "resume": "I am a developer.",
        "job": (
            "Backend Engineer. Python, Django, PostgreSQL, AWS required. 3+ years exp."
        ),
        "expected_score_min": 0,
        "expected_score_max": 100,  # score irrelevant — just check low_confidence=True
        "check_low_confidence": True,
        "required_gap_keyword": None,
        "required_strength_keyword": None,
    },
    {
        "id": "tc07",
        "description": "Weak match: nurse applying to software engineer role",
        "resume": (
            "Pat Johnson | Registered Nurse, 6 years ICU\n"
            "Patient care, medication administration, EMR systems, team coordination.\n"
            "BSN, licensed RN. Strong communication and critical thinking."
        ),
        "job": (
            "Software Engineer\n"
            "3+ years Python or Java. REST APIs, SQL, Git, CI/CD required.\n"
            "CS degree or equivalent preferred."
        ),
        "expected_score_min": 0,
        "expected_score_max": 30,
        "required_gap_keyword": "python",
        "required_strength_keyword": None,
    },
    {
        "id": "tc08",
        "description": "Strong match: DevOps engineer vs DevOps role",
        "resume": (
            "Riley Park | DevOps Engineer, 6 years\n"
            "Terraform, Kubernetes, Docker, Jenkins, AWS, GCP, Python scripting.\n"
            "Reduced deployment time 40%. On-call incident response. BS CS."
        ),
        "job": (
            "Senior DevOps / Platform Engineer\n"
            "5+ years. Terraform, Kubernetes, CI/CD pipelines (Jenkins or GitHub Actions).\n"
            "Cloud: AWS required, GCP a plus. Python scripting. Incident management."
        ),
        "expected_score_min": 80,
        "expected_score_max": 100,
        "required_gap_keyword": None,
        "required_strength_keyword": "terraform",
    },
    {
        "id": "tc09",
        "description": "Partial match: frontend dev applying to fullstack requiring backend",
        "resume": (
            "Casey Wu | Frontend Developer, 3 years\n"
            "React, TypeScript, CSS, HTML, Figma, Jest. Built 5 production UIs.\n"
            "No backend experience. No SQL. BA Design."
        ),
        "job": (
            "Full Stack Engineer\n"
            "React required. Node.js or Python backend required. PostgreSQL required.\n"
            "2+ years fullstack production experience."
        ),
        "expected_score_min": 30,
        "expected_score_max": 60,
        "required_gap_keyword": "node",
        "required_strength_keyword": "react",
    },
    {
        "id": "tc10",
        "description": "Strong match: Android dev vs Android role",
        "resume": (
            "Morgan Davis | Android Developer, 5 years\n"
            "Kotlin, Java, Jetpack Compose, MVVM, Retrofit, Room, Coroutines.\n"
            "Published 4 apps on Play Store. BS CS, 2 years at Google."
        ),
        "job": (
            "Senior Android Engineer\n"
            "4+ years Android. Kotlin required, Java a plus. Jetpack Compose, MVVM.\n"
            "Experience with REST APIs and local databases (Room). Play Store shipping required."
        ),
        "expected_score_min": 82,
        "expected_score_max": 100,
        "required_gap_keyword": None,
        "required_strength_keyword": "kotlin",
    },
]


# ── Scoring helpers ──────────────────────────────────────────────────────────

def score_case(tc: dict) -> dict:
    """Run one test case, return result dict."""
    try:
        result = score_match(tc["resume"], tc["job"])
    except Exception as e:
        return {
            "id": tc["id"],
            "description": tc["description"],
            "status": "ERROR",
            "error": str(e),
            "overall_score": None,
            "score_pass": False,
            "gap_pass": None,
            "strength_pass": None,
            "low_confidence_pass": None,
            "passed": False,
        }

    score = result.overall_score
    lo, hi = tc["expected_score_min"], tc["expected_score_max"]
    score_pass = lo <= score <= hi

    # Gap keyword check
    gap_kw = tc.get("required_gap_keyword")
    gap_absent_kw = tc.get("required_gap_absent")
    gaps_text = " ".join(result.gaps).lower()
    if gap_kw:
        gap_pass = gap_kw.lower() in gaps_text
    elif gap_absent_kw:
        gap_pass = gap_absent_kw.lower() not in gaps_text  # should NOT appear as a gap
    else:
        gap_pass = True  # no check required

    # Strength keyword check
    str_kw = tc.get("required_strength_keyword")
    strengths_text = " ".join(result.strengths).lower()
    strength_pass = (str_kw.lower() in strengths_text) if str_kw else True

    # Low confidence check
    check_lc = tc.get("check_low_confidence", False)
    lc_pass = result.low_confidence if check_lc else True

    passed = score_pass and gap_pass and strength_pass and lc_pass

    return {
        "id": tc["id"],
        "description": tc["description"],
        "status": "OK",
        "error": "",
        "overall_score": score,
        "expected_range": f"{lo}-{hi}",
        "score_pass": score_pass,
        "gap_pass": gap_pass,
        "strength_pass": strength_pass,
        "low_confidence_pass": lc_pass if check_lc else "N/A",
        "passed": passed,
        "verdict": result.verdict,
        "gaps_preview": "; ".join(result.gaps[:2]),
        "strengths_preview": "; ".join(result.strengths[:2]),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Running {len(TEST_CASES)} eval cases...\n")
    rows = []
    passed = 0

    for tc in TEST_CASES:
        print(f"  [{tc['id']}] {tc['description'][:60]}...", end=" ", flush=True)
        row = score_case(tc)
        rows.append(row)
        status = "✓ PASS" if row["passed"] else "✗ FAIL"
        print(f"{status} (score={row['overall_score']})")
        if row["passed"]:
            passed += 1

    # Write CSV
    out_path = os.path.join(os.path.dirname(__file__), "results.csv")
    fieldnames = [
        "id", "description", "status", "error", "overall_score",
        "expected_range", "score_pass", "gap_pass", "strength_pass",
        "low_confidence_pass", "passed", "verdict", "gaps_preview", "strengths_preview",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    total = len(TEST_CASES)
    pct = passed / total * 100
    print(f"\n{'='*50}")
    print(f"Overall score: {passed}/{total} ({pct:.1f}%)")
    print(f"Results written to: {out_path}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

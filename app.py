"""
app.py
Agentic Tester App — Gemini edition.
Simple 3-step UI: enter API key → upload PDF → run agents.
"""

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent))

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agentic Tester App",
    page_icon="🤖",
    layout="centered",
)

st.title("🤖 Agentic Tester App")
st.caption("Gemini-powered · Agent A → Agent B → Agent C (max 5 review loops)")
st.divider()


# ── Step 1: API key ───────────────────────────────────────────────────────────
st.subheader("Step 1 — Gemini API key")
api_key = st.text_input(
    "Enter your Gemini API key",
    type="password",
    placeholder="AIza...",
    help="Get a free key at https://aistudio.google.com/app/apikey",
)

if not api_key:
    st.info("Enter your Gemini API key to continue.")
    st.stop()

st.success("API key entered ✓")
st.divider()


# ── Step 2: Upload PDF ────────────────────────────────────────────────────────
st.subheader("Step 2 — Upload requirements PDF")
uploaded = st.file_uploader("Choose a PDF file", type=["pdf"])

if not uploaded:
    st.info("Upload a PDF to continue.")
    st.stop()


def extract_pdf_text(file) -> str:
    """Extract all text from an uploaded PDF file."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name
    reader = PdfReader(tmp_path)
    pages = [p.extract_text() for p in reader.pages if p.extract_text()]
    return "\n\n".join(pages)


with st.spinner("Reading PDF..."):
    try:
        doc_text = extract_pdf_text(uploaded)
    except Exception as e:
        st.error(f"Could not read PDF: {e}")
        st.stop()

st.success(f"PDF loaded: **{uploaded.name}** — {len(doc_text):,} characters extracted ✓")
st.divider()


# ── Step 3: Run agents ────────────────────────────────────────────────────────
st.subheader("Step 3 — Run agents")


def _report_to_md(report: dict, attempts: int) -> str:
    verdict = report.get("verdict", "?")
    lines = [
        f"# Review Report",
        f"**Verdict:** {verdict}  |  **Score:** {report.get('score', 0)}/100  |  **Attempts:** {attempts}",
        f"\n**Summary:** {report.get('summary', '')}",
    ]
    for key, title in [
        ("hallucinations", "Hallucinations"),
        ("missing_tests",  "Missing Tests"),
        ("issues",         "Code Issues"),
    ]:
        items = report.get(key, [])
        lines.append(f"\n## {title}")
        lines += ([f"- {i}" for i in items] if items else ["_None._"])
    if report.get("fix_instructions"):
        lines.append(f"\n## Fix Instructions\n{report['fix_instructions']}")
    return "\n".join(lines)


if st.button("🚀 Run all agents", type="primary"):

    # Live log area
    log_area = st.empty()
    logs: list[str] = []

    def log(msg: str):
        logs.append(msg)
        log_area.code("\n".join(logs[-20:]), language=None)

    try:
        from agents.pipeline import build_pipeline

        pipeline = build_pipeline()
        result = pipeline.invoke(
            {
                "api_key": api_key,
                "document_text": doc_text,
                "requirements": [],
                "test_code": "",
                "report": {},
                "version": 0,
                "attempt": 0,
            },
            config={"configurable": {"log": log}},
        )

        final_code  = result["test_code"]
        report      = result["report"]
        attempts    = result["attempt"]
        requirements = result["requirements"]

        log("")
        log("=" * 50)
        log(f"🏁 Done — Verdict: {report.get('verdict')} | Attempts: {attempts}")
        log("=" * 50)

        # Save to output/
        Path("output").mkdir(exist_ok=True)
        Path("output/final_tests.py").write_text(final_code)
        Path("output/requirements.json").write_text(json.dumps(requirements, indent=2))
        Path("output/review_report.md").write_text(_report_to_md(report, attempts))

        # Store in session for display
        st.session_state.update({
            "done": True,
            "requirements": requirements,
            "final_code": final_code,
            "report": report,
            "attempts": attempts,
        })

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.exception(e)


# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.get("done"):
    st.divider()
    st.subheader("Results")

    report   = st.session_state["report"]
    reqs     = st.session_state["requirements"]
    code     = st.session_state["final_code"]
    attempts = st.session_state["attempts"]
    verdict  = report.get("verdict", "?")
    score    = report.get("score", 0)

    # Metrics row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Verdict",    verdict)
    c2.metric("Score",      f"{score}/100")
    c3.metric("Attempts",   f"{attempts}/5")
    c4.metric("Requirements", len(reqs))

    # Tabs
    tab_code, tab_reqs, tab_review = st.tabs(
        ["📄 Final tests", "📋 Requirements", "🔍 Review report"]
    )

    with tab_code:
        st.code(code, language="python")
        st.download_button("⬇️ Download final_tests.py", code, "final_tests.py", "text/x-python")

    with tab_reqs:
        for req in reqs:
            label = f"{req.get('id')} — {req.get('feature')} [{req.get('category')}]"
            with st.expander(label):
                st.write(f"**Description:** {req.get('description')}")
                if req.get("steps"):
                    st.write("**Steps:**")
                    for s in req["steps"]:
                        st.write(f"  - {s}")
                st.write(f"**Expected result:** {req.get('expected_result')}")

    with tab_review:
        st.write(f"**Summary:** {report.get('summary')}")

        for key, title, ok_msg in [
            ("hallucinations", "🔴 Hallucinations",  "No hallucinations."),
            ("missing_tests",  "🟠 Missing tests",   "All requirements covered."),
            ("issues",         "🔵 Code issues",     "No issues found."),
        ]:
            items = report.get(key, [])
            with st.expander(f"{title} ({len(items)})", expanded=bool(items)):
                if items:
                    for item in items:
                        st.write(f"- {item}")
                else:
                    st.success(ok_msg)

        if report.get("fix_instructions"):
            with st.expander("📝 Fix instructions (last round)"):
                st.code(report["fix_instructions"], language=None)

        # Downloads
        st.divider()
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇️ requirements.json",
                json.dumps(reqs, indent=2),
                "requirements.json",
                "application/json",
            )
        with d2:
            st.download_button(
                "⬇️ review_report.md",
                _report_to_md(report, attempts),
                "review_report.md",
                "text/markdown",
            )

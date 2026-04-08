# 🤖 Agentic Tester App

A Gemini-powered Streamlit app that extracts requirements from a PDF and generates Playwright tests using a 4-agent pipeline (Agent A → DOM Fetch → Agent B → Agent C with review loop). Agent B uses **real locators fetched live from the application under test**, and Agent C **validates those locators against the live DOM** with an accuracy score.

PLEASE FIND THE LATEST OUTPUT - 'AGENTIC TESTER APP.pdf'

## Prerequisites

- Python 3.10 or higher
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free)
- Network access to the application under test (for DOM fetching)

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd agentic_tester_app
```

### 2. Create a virtual environment

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies include: `streamlit`, `pypdf`, `langchain`, `langchain-google-genai`, `langgraph`, `requests`, `beautifulsoup4`.

## Running the App

```bash
streamlit run app.py
```

This opens the app in your browser (typically at `http://localhost:8501`).

## Usage

1. **Enter your Gemini API key.**
2. **Enter the base URL** of the application under test (e.g. `https://your-app.com`). This is used to fetch real page locators for test generation and validation.
3. **Upload a requirements PDF** — the app extracts the text automatically.
4. **Click "Run all agents"** to start the pipeline:
   - **Agent A** — Extracts structured requirements from the PDF.
   - **DOM Fetch** — Fetches the live page at the base URL and captures all interactive elements (inputs, buttons, links, labels, roles, `data-testid` attributes, etc.) as a locator reference.
   - **Agent B** — Generates Playwright test code using **only real locators** from the DOM snapshot. Invented/dummy selectors are not permitted.
   - **Agent C** — Reviews the tests against both the requirements and the live DOM snapshot. Reports a **locator accuracy score** (0–100) indicating what percentage of locators in the generated tests match real page elements. Iterates up to 5 times, feeding corrections back to Agent B until tests pass or the limit is reached.
5. View results, download the generated test file, and check the review report.

Output files are saved to the `output/` directory:
- `final_tests.py` — Generated Playwright tests
- `requirements.json` — Extracted requirements
- `review_report.md` — Review summary including locator accuracy score

## Results Summary

The results panel displays five metrics:

| Metric | Description |
|---|---|
| Verdict | PASS or FAIL |
| Score | Overall quality against requirements (0–100) |
| Locator Accuracy | % of locators verified against the live DOM (0–100) |
| Attempts | Number of review iterations used (max 5) |
| Requirements | Number of requirements extracted |

A **PASS** verdict requires: score ≥ 80, locator accuracy ≥ 80, no hallucinated tests, no missing requirement coverage, and no dummy/invented locators.

## Project Structure

```
agentic_tester_app/
├── app.py                   # Streamlit UI and pipeline orchestration
├── requirements.txt         # Python dependencies
├── agents/
│   ├── __init__.py
│   ├── agent_a.py           # Requirement extraction agent
│   ├── agent_b.py           # Test generation agent (uses real DOM locators)
│   ├── agent_c.py           # Review and refinement agent (DOM locator validation)
│   ├── dom_fetcher.py       # Fetches live page and extracts locator elements
│   └── pipeline.py          # LangGraph pipeline (A → DOM Fetch → B → C loop)
└── prompts/
    ├── agent_a_prompt.txt   # Prompt for Agent A
    ├── agent_b_prompt.txt   # Prompt for Agent B
    └── agent_c_prompt.txt   # Prompt for Agent C
```

## Deactivating the Virtual Environment

```bash
deactivate
```

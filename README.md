# 🤖 Agentic Tester App

A Gemini-powered Streamlit app that extracts requirements from a PDF and generates Playwright tests using a 3-agent pipeline (Agent A → Agent B → Agent C with review loop).

## Prerequisites

- Python 3.10 or higher
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free)

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

## Running the App

```bash
streamlit run app.py
```

This opens the app in your browser (typically at `http://localhost:8501`).

## Usage

1. **Enter your Gemini API key** in the sidebar.
2. **Upload a requirements PDF** — the app extracts the text automatically.
3. **Click "Run all agents"** to start the pipeline:
   - **Agent A** — Extracts structured requirements from the PDF.
   - **Agent B** — Generates Playwright test code from the requirements.
   - **Agent C** — Reviews and refines the tests (up to 5 iterations).
4. View results, download the generated test file, and check the review report.

Output files are saved to the `output/` directory:
- `final_tests.py` — Generated Playwright tests
- `requirements.json` — Extracted requirements
- `review_report.md` — Review summary

## Project Structure

```
agentic_tester_app/
├── app.py                  # Streamlit UI and pipeline orchestration
├── requirements.txt        # Python dependencies
├── agents/
│   ├── __init__.py
│   ├── agent_a.py          # Requirement extraction agent
│   ├── agent_b.py          # Test generation agent
│   └── agent_c.py          # Review and refinement agent
└── prompts/
    ├── agent_a_prompt.txt   # Prompt for Agent A
    ├── agent_b_prompt.txt   # Prompt for Agent B
    └── agent_c_prompt.txt   # Prompt for Agent C
```

## Deactivating the Virtual Environment

```bash
deactivate
```

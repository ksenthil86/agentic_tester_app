"""
agents/agent_c.py - REVIEWER AGENT
Reviews Playwright test code using a LangChain chain:
    prompt | llm | JsonOutputParser

Loops up to MAX_ATTEMPTS times, passing the critique back to Agent B on FAIL.
Also verifies that locators in the test code match real elements from the live
page DOM snapshot (dom_snapshot) and reports a locator_accuracy_score."""

import json
from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

import agents.agent_b as agent_b

MODEL       = "gemini-2.5-flash"
MAX_ATTEMPTS = 5
PROMPT_FILE  = Path(__file__).parent.parent / "prompts" / "agent_c_prompt.txt"


def _build_chain(api_key: str):
    """Build the LangChain chain: prompt | llm | parser."""
    prompt = ChatPromptTemplate.from_template(PROMPT_FILE.read_text())
    llm    = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, temperature=0)
    parser = JsonOutputParser()
    return prompt | llm | parser


def _safe_invoke(chain, inputs: dict, attempt: int) -> dict:
    """
    Invoke the chain and return the parsed report.
    Falls back to a minimal FAIL dict if parsing fails so the loop can continue.
    """
    try:
        return chain.invoke(inputs)
    except Exception as e:
        return {
            "verdict":               "FAIL",
            "score":                 0,
            "locator_accuracy_score": 0,
            "hallucinations":        [],
            "missing_tests":         [f"Review parse error on attempt {attempt}: {e}"],
            "dummy_locators":        [],
            "verified_locators":     [],
            "issues":                ["Unparseable response — requesting regeneration."],
            "summary":               "Review failed to parse.",
            "fix_instructions":      "Regenerate the full test suite from scratch.",
        }


def run(api_key: str, requirements: list, initial_test_code: str,
        dom_snapshot: str = "", locked_locators: list | None = None,
        log=None) -> tuple:
    """
    Review-and-rewrite loop.

    Args:
        api_key:           Gemini API key.
        requirements:      Requirements list from Agent A.
        initial_test_code: First version of tests from Agent B.
        dom_snapshot:      Text DOM snapshot from dom_fetcher for locator validation.
        locked_locators:   Previously verified locator expressions to preserve.
        log:               Optional callable(str) for status messages.

    Returns:
        (final_test_code, final_report, total_attempts)
    """
    chain        = _build_chain(api_key)
    current_code = initial_test_code
    report       = {}
    version      = 1      # Agent B already wrote v1
    all_locked   = list(locked_locators or [])

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if log:
            log(f"🔍 Agent C: Reviewing tests (attempt {attempt}/{MAX_ATTEMPTS})...")

        report = _safe_invoke(chain, {
            "requirements": json.dumps(requirements, indent=2),
            "test_code":    current_code,
            "dom_snapshot": dom_snapshot or "No DOM snapshot available.",
        }, attempt)

        verdict                = report.get("verdict", "FAIL")
        score                  = report.get("score", 0)
        locator_accuracy_score = report.get("locator_accuracy_score", 0)

        # Use latest verified locators only (not accumulated across versions)
        # Accumulating causes stale entries when Agent B patches the code
        verified = report.get("verified_locators", [])
        all_locked = sorted(set(verified))

        if log:
            log(f"   Verdict: {verdict} | Score: {score}/100 | Locator Accuracy: {locator_accuracy_score}/100")
            if verified:
                log(f"   🔒 {len(all_locked)} locators locked for next rewrite")

        if verdict == "PASS":
            if log:
                log(f"✅ Agent C: Tests passed on attempt {attempt}.")
            break

        if attempt == MAX_ATTEMPTS:
            if log:
                log(f"⚠️  Agent C: Reached max {MAX_ATTEMPTS} attempts.")
            break

        # FAIL — send critique to Agent B for a rewrite
        version += 1
        if log:
            log(f"🔁 Sending critique to Agent B for rewrite (v{version})...")

        current_code = agent_b.run(
            api_key=api_key,
            requirements=requirements,
            version=version,
            critique=report.get("fix_instructions", ""),
            dom_snapshot=dom_snapshot,
            locked_locators=all_locked,
            previous_code=current_code,
            log=log,
        )

    return current_code, report, attempt

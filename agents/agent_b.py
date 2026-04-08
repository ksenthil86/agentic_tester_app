"""
agents/agent_b.py - TEST GENERATION AGENT
Generates Playwright (pytest) test code from requirements using a LangChain chain:
    prompt | llm | StrOutputParser

Agent C passes a critique string on rewrites; it is injected into the prompt
via the {critique} placeholder defined in agent_b_prompt.txt.

The agent receives a dom_snapshot (text) from the pipeline so it uses real
locators extracted from the live page instead of invented ones.
"""

import re
from datetime import datetime
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

MODEL = "gemini-2.5-flash"
PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "agent_b_prompt.txt"


def _build_chain(api_key: str):
    """Build the LangChain chain: prompt | llm | parser."""
    prompt = ChatPromptTemplate.from_template(PROMPT_FILE.read_text())
    llm    = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, temperature=0.1)
    parser = StrOutputParser()
    return prompt | llm | parser


def _strip_fences(code: str) -> str:
    """Remove markdown code fences if Gemini wraps the output."""
    code = code.strip()
    code = re.sub(r"^```(?:python)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    return code.strip()


def _critique_block(critique: str) -> str:
    """Format the critique section injected into the prompt on rewrites."""
    if not critique:
        return ""
    return (
        "IMPORTANT — This is a PATCH rewrite. Fix ONLY the specific issues listed below.\n"
        "Do NOT regenerate the entire test suite. Keep all working code intact.\n"
        "Only modify the specific test functions and locators mentioned:\n\n"
        + critique
        + "\n---\n"
    )


def _locked_locators_block(locked_locators: list) -> str:
    """Format the locked-locators section — locators verified correct that must not change."""
    if not locked_locators:
        return ""
    lines = [
        "LOCKED LOCATORS — These locators have been verified against the live DOM.",
        "Do NOT change, replace, or remove any of the locators listed below.",
        "They are correct and must remain exactly as shown:",
        "",
    ]
    for loc in locked_locators:
        lines.append(f"  ✓ {loc}")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def _previous_code_block(previous_code: str) -> str:
    """Format the previous code section so Agent B can patch rather than regenerate."""
    if not previous_code:
        return ""
    return (
        "PREVIOUS TEST CODE — This is the current version of the test suite.\n"
        "Modify ONLY the specific functions / locators mentioned in the critique above.\n"
        "Keep ALL other code exactly as-is. Output the full file with your patches applied.\n\n"
        + previous_code
        + "\n---\n"
    )


def run(api_key: str, requirements: list, version: int = 1,
        critique: str = "", dom_snapshot: str = "",
        locked_locators: list | None = None,
        previous_code: str = "", log=None) -> str:
    """
    Generate Playwright test code.

    Args:
        api_key:          Gemini API key.
        requirements:     List of requirement dicts from Agent A.
        version:          Iteration number (1 = first run, 2+ = rewrites).
        critique:         Fix instructions from Agent C (empty on first run).
        dom_snapshot:     Text representation of the live page DOM from dom_fetcher.
        locked_locators:  List of verified-good locator strings from Agent C.
        previous_code:    Previous test code for patch-based rewrites (empty on first run).
        log:              Optional callable(str) for status messages.

    Returns:
        Generated Python test code as a string.
    """
    if log:
        log(f"🤖 Agent B: Generating Playwright tests (version {version})...")

    import json
    chain = _build_chain(api_key)
    code  = _strip_fences(
        chain.invoke({
            "requirements":    json.dumps(requirements, indent=2),
            "critique":        _critique_block(critique),
            "dom_snapshot":    dom_snapshot or "No DOM snapshot available.",
            "locked_locators": _locked_locators_block(locked_locators or []),
            "previous_code":   _previous_code_block(previous_code),
        })
    )

    if "# Generated" not in code:
        code = (
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# Version:   {version}\n\n"
            + code
        )

    if log:
        log(f"✅ Agent B: Generated {code.count('def test_')} test functions (v{version}).")

    return code

"""
agents/agent_b.py - TEST GENERATION AGENT
Generates Playwright (pytest) test code from requirements using a LangChain chain:
    prompt | llm | StrOutputParser

Agent C passes a critique string on rewrites; it is injected into the prompt
via the {critique} placeholder defined in agent_b_prompt.txt.
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
        "IMPORTANT — This is a rewrite. Fix ALL issues listed below:\n\n"
        + critique
        + "\n---\n"
    )


def run(api_key: str, requirements: list, version: int = 1,
        critique: str = "", log=None) -> str:
    """
    Generate Playwright test code.

    Args:
        api_key:      Gemini API key.
        requirements: List of requirement dicts from Agent A.
        version:      Iteration number (1 = first run, 2+ = rewrites).
        critique:     Fix instructions from Agent C (empty on first run).
        log:          Optional callable(str) for status messages.

    Returns:
        Generated Python test code as a string.
    """
    if log:
        log(f"🤖 Agent B: Generating Playwright tests (version {version})...")

    import json
    chain = _build_chain(api_key)
    code  = _strip_fences(
        chain.invoke({
            "requirements": json.dumps(requirements, indent=2),
            "critique":     _critique_block(critique),
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

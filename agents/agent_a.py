"""
agents/agent_a.py - ANALYST AGENT
Extracts structured requirements from PDF text using a LangChain chain:
    prompt | llm | JsonOutputParser
"""

from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

MODEL = "gemini-2.5-flash"
PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "agent_a_prompt.txt"


def _build_chain(api_key: str):
    """Build the LangChain chain: prompt | llm | parser."""
    prompt = ChatPromptTemplate.from_template(PROMPT_FILE.read_text())
    llm    = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, temperature=0)
    parser = JsonOutputParser()
    return prompt | llm | parser


def run(api_key: str, document_text: str, log=None) -> list:
    """
    Extract requirements from document text.

    Args:
        api_key:       Gemini API key.
        document_text: Full text extracted from the PDF.
        log:           Optional callable(str) for status messages.

    Returns:
        List of requirement dicts.
    """
    if log:
        log("🤖 Agent A: Extracting requirements via Gemini...")

    chain = _build_chain(api_key)
    requirements = chain.invoke({"document_text": document_text})

    if log:
        log(f"✅ Agent A: Extracted {len(requirements)} requirements.")

    return requirements

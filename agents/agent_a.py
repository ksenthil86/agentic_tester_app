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


def run(api_key: str, document_text: str, log=None) -> dict:
    """
    Extract requirements from document text.

    Args:
        api_key:       Gemini API key.
        document_text: Full text extracted from the PDF.
        log:           Optional callable(str) for status messages.

    Returns:
        Dict with keys: "requirements" (list of dicts), "page_urls" (list of str).
    """
    if log:
        log("🤖 Agent A: Extracting requirements via Gemini...")

    chain = _build_chain(api_key)
    result = chain.invoke({"document_text": document_text})

    # Handle both old format (plain list) and new format (dict)
    if isinstance(result, list):
        requirements = result
        page_urls = []
    else:
        requirements = result.get("requirements", result if isinstance(result, list) else [])
        page_urls = result.get("page_urls", [])

    if log:
        log(f"✅ Agent A: Extracted {len(requirements)} requirements, "
            f"{len(page_urls)} page URLs.")

    return {"requirements": requirements, "page_urls": page_urls}

"""
agents/pipeline.py
LangGraph pipeline: Agent A → DOM Fetch → Agent B → Agent C (review loop, max 5 attempts).

Graph layout:
    agent_a ──► dom_fetch ──► agent_b ──► agent_c ──► (PASS or max attempts?) ──► END
                                  ▲                              │ FAIL
                                  └──────────────────────────────┘

Key features:
- Multi-page DOM crawl: base URL + internal links + page URLs from requirements.
- Locator locking: verified-good locators from Agent C are frozen across rewrites.
- Incremental patching: Agent B only fixes broken parts, not the whole suite.
"""

import json
from typing import TypedDict
from urllib.parse import urljoin

from langgraph.graph import END, StateGraph

import agents.agent_a as agent_a
import agents.agent_b as agent_b
import agents.agent_c as agent_c
from agents.dom_fetcher import build_locator_registry, registry_to_text

MAX_ATTEMPTS = 5


class PipelineState(TypedDict):
    api_key: str
    base_url: str
    document_text: str
    requirements: list
    page_urls: list
    dom_snapshot: str
    test_code: str
    report: dict
    locked_locators: list
    version: int
    attempt: int


# ── Node helpers ──────────────────────────────────────────────────────────────

def _log(config, msg: str):
    fn = config.get("configurable", {}).get("log")
    if fn:
        fn(msg)


# ── Nodes ─────────────────────────────────────────────────────────────────────

def node_agent_a(state: PipelineState, config) -> dict:
    _log(config, "=" * 50)
    _log(config, "▶  AGENT A — Extract requirements")
    _log(config, "=" * 50)
    result = agent_a.run(
        api_key=state["api_key"],
        document_text=state["document_text"],
        log=config.get("configurable", {}).get("log"),
    )
    _log(config, "")
    return {
        "requirements": result["requirements"],
        "page_urls":    result.get("page_urls", []),
    }


def node_fetch_dom(state: PipelineState, config) -> dict:
    base_url = state.get("base_url", "").strip()
    if not base_url:
        _log(config, "⚠️  DOM Fetch: No base URL provided — skipping.")
        return {"dom_snapshot": "No base URL provided. No DOM snapshot available."}

    _log(config, "=" * 50)
    _log(config, f"▶  DOM FETCH — Multi-page crawl from {base_url}")
    _log(config, "=" * 50)

    # Build full URLs from page_urls extracted by Agent A
    page_urls = state.get("page_urls", [])
    extra_urls = [urljoin(base_url, p) for p in page_urls if p]

    log_fn = config.get("configurable", {}).get("log")
    registry = build_locator_registry(
        base_url=base_url,
        extra_urls=extra_urls,
        max_pages=10,
        log=log_fn,
    )

    total = sum(len(p["elements"]) for p in registry.get("pages", []))
    if log_fn:
        log_fn(f"✅ DOM Fetch: {len(registry['pages'])} page(s), "
               f"{total} total elements captured. Saved to output/locators.json")
    _log(config, "")
    return {"dom_snapshot": registry_to_text(registry)}


def node_agent_b(state: PipelineState, config) -> dict:
    version = state.get("version", 0) + 1
    attempt = state.get("attempt", 0)

    if version == 1:
        _log(config, "=" * 50)
        _log(config, "▶  AGENT B — Generate Playwright tests (v1)")
        _log(config, "=" * 50)
    else:
        _log(config, f"🔁 Sending critique to Agent B for rewrite (v{version})...")

    critique = state.get("report", {}).get("fix_instructions", "") if attempt > 0 else ""

    # On rewrites, pass the previous test code so Agent B can patch instead of regenerating
    previous_code = state.get("test_code", "") if version > 1 else ""

    test_code = agent_b.run(
        api_key=state["api_key"],
        requirements=state["requirements"],
        version=version,
        critique=critique,
        dom_snapshot=state.get("dom_snapshot", ""),
        locked_locators=state.get("locked_locators", []) if version > 1 else None,
        previous_code=previous_code,
        log=config.get("configurable", {}).get("log"),
    )

    if version == 1:
        _log(config, "")
        _log(config, "=" * 50)
        _log(config, "▶  AGENT C — Review loop (max 5 attempts)")
        _log(config, "=" * 50)

    return {"test_code": test_code, "version": version}


def node_agent_c(state: PipelineState, config) -> dict:
    attempt = state.get("attempt", 0) + 1
    log_fn = config.get("configurable", {}).get("log")

    if log_fn:
        log_fn(f"🔍 Agent C: Reviewing tests (attempt {attempt}/{MAX_ATTEMPTS})...")

    chain = agent_c._build_chain(state["api_key"])
    report = agent_c._safe_invoke(
        chain,
        {
            "requirements": json.dumps(state["requirements"], indent=2),
            "test_code": state["test_code"],
            "dom_snapshot": state.get("dom_snapshot", "") or "No DOM snapshot available.",
        },
        attempt,
    )

    verdict                = report.get("verdict", "FAIL")
    score                  = report.get("score", 0)
    locator_accuracy_score = report.get("locator_accuracy_score", 0)

    if log_fn:
        log_fn(f"   Verdict: {verdict} | Score: {score}/100 | Locator Accuracy: {locator_accuracy_score}/100")

    # ── Locator locking: use latest verified locators (not accumulated) ──
    # Only the locators verified in this review are relevant to the current code.
    # Accumulating across versions causes stale entries that confuse Agent B.
    verified = report.get("verified_locators", [])
    new_locked = sorted(set(verified))
    if verified and log_fn:
        log_fn(f"   🔒 {len(new_locked)} verified locators locked for next rewrite")

    if verdict == "PASS" and log_fn:
        log_fn(f"✅ Agent C: Tests passed on attempt {attempt}.")
    elif attempt >= MAX_ATTEMPTS and log_fn:
        log_fn(f"⚠️  Agent C: Reached max {MAX_ATTEMPTS} attempts.")

    return {"report": report, "attempt": attempt, "locked_locators": new_locked}


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_after_review(state: PipelineState) -> str:
    verdict = state.get("report", {}).get("verdict", "FAIL")
    attempt = state.get("attempt", 0)
    if verdict == "PASS" or attempt >= MAX_ATTEMPTS:
        return "end"
    return "rewrite"


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_pipeline():
    """Compile and return the LangGraph pipeline."""
    workflow = StateGraph(PipelineState)

    workflow.add_node("agent_a",    node_agent_a)
    workflow.add_node("fetch_dom",  node_fetch_dom)
    workflow.add_node("agent_b",    node_agent_b)
    workflow.add_node("agent_c",    node_agent_c)

    workflow.set_entry_point("agent_a")
    workflow.add_edge("agent_a", "fetch_dom")
    workflow.add_edge("fetch_dom", "agent_b")
    workflow.add_edge("agent_b", "agent_c")
    workflow.add_conditional_edges(
        "agent_c",
        _route_after_review,
        {"end": END, "rewrite": "agent_b"},
    )

    return workflow.compile()

"""
agents/pipeline.py
LangGraph pipeline: Agent A → Agent B → Agent C (review loop, max 5 attempts).

Graph layout:
    agent_a ──► agent_b ──► agent_c ──► (PASS or max attempts?) ──► END
                   ▲                              │ FAIL
                   └──────────────────────────────┘
"""

import json
from typing import TypedDict

from langgraph.graph import END, StateGraph

import agents.agent_a as agent_a
import agents.agent_b as agent_b
import agents.agent_c as agent_c

MAX_ATTEMPTS = 5


class PipelineState(TypedDict):
    api_key: str
    document_text: str
    requirements: list
    test_code: str
    report: dict
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
    requirements = agent_a.run(
        api_key=state["api_key"],
        document_text=state["document_text"],
        log=config.get("configurable", {}).get("log"),
    )
    _log(config, "")
    return {"requirements": requirements}


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

    test_code = agent_b.run(
        api_key=state["api_key"],
        requirements=state["requirements"],
        version=version,
        critique=critique,
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
        },
        attempt,
    )

    verdict = report.get("verdict", "FAIL")
    score = report.get("score", 0)

    if log_fn:
        log_fn(f"   Verdict: {verdict} | Score: {score}/100")

    if verdict == "PASS" and log_fn:
        log_fn(f"✅ Agent C: Tests passed on attempt {attempt}.")
    elif attempt >= MAX_ATTEMPTS and log_fn:
        log_fn(f"⚠️  Agent C: Reached max {MAX_ATTEMPTS} attempts.")

    return {"report": report, "attempt": attempt}


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

    workflow.add_node("agent_a", node_agent_a)
    workflow.add_node("agent_b", node_agent_b)
    workflow.add_node("agent_c", node_agent_c)

    workflow.set_entry_point("agent_a")
    workflow.add_edge("agent_a", "agent_b")
    workflow.add_edge("agent_b", "agent_c")
    workflow.add_conditional_edges(
        "agent_c",
        _route_after_review,
        {"end": END, "rewrite": "agent_b"},
    )

    return workflow.compile()

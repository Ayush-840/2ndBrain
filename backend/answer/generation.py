"""Answer synthesis over retrieved context.

Turns hybrid-search results into a cited, conversational answer. The model
must ground every claim in the numbered context blocks or say it does not
know; citations are [n] references back to the SearchResult list. Both
tiers (Anthropic cloud, OpenAI-compatible local) share one prompt builder so
routing is the *only* difference between them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from backend.answer.routing import RouteDecision
from backend.config import settings

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 6000  # cap on evidence sent to the model

SYSTEM_PROMPT = """\
You are the personal assistant inside the user's second-brain app.
You answer ONLY from the numbered evidence blocks in the conversation.
Rules:
- Cite evidence with bracketed numbers, e.g. [2], whenever you use it.
- If the evidence does not contain the answer, say so plainly — never invent.
- Evidence may be stale or superseded; note uncertainty when it matters.
- For follow-up questions, resolve references (e.g. "the one from last year")
  using the earlier turns of this conversation.
- Keep answers short and factual; this is a personal memory tool, not a chatbot.
"""


@dataclass
class AnswerResult:
    answer: str
    context_used: int  # how many results were sent as evidence


class LLMCallError(RuntimeError):
    """The chosen tier failed while generating."""


def build_context(results: list) -> str:
    """Numbered evidence blocks: [1] (source, score) text ..."""
    blocks = []
    budget = MAX_CONTEXT_CHARS
    for i, r in enumerate(results, start=1):
        text = (r.text or "").strip()
        if len(text) > 900:
            text = text[:900] + " …"
        block = f"[{i}] ({r.source}, score {r.score:.3f}) {text}"
        if budget - len(block) < 0:
            break
        budget -= len(block)
        blocks.append(block)
    return "\n\n".join(blocks)


def build_messages(
    question: str, results: list, history: list
) -> list[dict]:
    """Chat messages: prior turns + evidence-grounded user prompt."""
    messages = [{"role": t.role, "content": t.content} for t in history]
    context = build_context(results)
    user_prompt = f"Evidence:\n{context or '(no relevant evidence found)'}\n\nQuestion: {question}"
    messages.append({"role": "user", "content": user_prompt})
    return messages


def _call_cloud(messages: list[dict]) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.answer_max_tokens,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def _call_local(messages: list[dict]) -> str:
    base = settings.local_llm_base_url.rstrip("/")
    resp = httpx.post(
        f"{base}/chat/completions",
        json={
            "model": settings.local_llm_model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            "max_tokens": settings.answer_max_tokens,
            "temperature": 0.2,
        },
        timeout=90.0,
    )
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


def generate_answer(
    question: str, results: list, history: list, decision: RouteDecision
) -> AnswerResult:
    """Synthesize a cited answer using the routed model tier.

    Raises:
        LLMCallError: transport/API failure (endpoint maps it to 502).
    """
    messages = build_messages(question, results, history)
    try:
        if decision.provider == "local":
            answer = _call_local(messages)
        else:
            answer = _call_cloud(messages)
    except Exception as exc:  # noqa: BLE001 - normalize provider errors
        logger.warning("answer generation failed on %s: %s", decision.provider, exc)
        raise LLMCallError(f"{decision.provider} model call failed: {exc}") from exc

    if not answer:
        raise LLMCallError(f"{decision.provider} model returned an empty answer")
    return AnswerResult(answer=answer, context_used=len(results))

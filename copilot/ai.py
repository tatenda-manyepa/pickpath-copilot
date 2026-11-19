"""Asks Claude on Amazon Bedrock to explain an incident from the evidence pack.

The model is told to use only the evidence it is given, to cite evidence IDs,
and to say so when the evidence is not enough. Its answer is checked before it
is shown: any citation that does not match real evidence is flagged.
"""
from __future__ import annotations

import json
import os
import re

from .evidence import EvidencePack

SYSTEM_PROMPT = """You are PickPath Copilot, an incident investigation assistant for engineers at an automated warehouse.

Rules you must follow:
- You are read-only and advisory. You never send commands to robots, chargers, conveyors or control systems. An engineer decides and acts.
- Use ONLY the evidence provided. Do not invent robots, codes, times or tickets.
- Cite evidence by its ID, like E12. Every claim about the site must be backed by at least one ID.
- Look for the root cause, not just the symptom. The symptom and the cause are often in different parts of the site.
- Past tickets can look similar but have a different cause. Compare the evidence before you call a past ticket a match, and say which look-alikes you ruled out and why.
- Some evidence is unrelated noise. Say so if it could mislead an engineer.
- If the evidence does not support a confident answer, set status to "insufficient_evidence" and say what to check.
- Write in plain, short sentences for a busy engineer.
- Keep it concise: at most 8 evidence items, 3 ruled_out items and 3 check_next items.

Answer with a single JSON object and nothing else, using this structure:
{
  "status": "recommendation" or "insufficient_evidence",
  "likely_cause": "one sentence",
  "confidence": "high", "medium" or "low",
  "reasoning": "two or three sentences linking symptom to cause",
  "evidence": [{"id": "E12", "why": "what this record shows"}],
  "ruled_out": [{"what": "alternative explanation or look-alike ticket", "why": "why it does not fit", "ids": ["E3"]}],
  "similar_incident": {"ticket": "INC-0000 or empty", "why": "why it matches"},
  "runbook": {"id": "RB-00 or empty", "next_step": "the first step to try now"},
  "check_next": ["short check an engineer can do to confirm"],
  "prevention": "one sentence on stopping this recurring, and whether a simple rule or alert would do"
}"""


def build_prompt(pack: EvidencePack) -> str:
    return (f"Incident reported at {pack.as_of:%a %d %b %Y %H:%M}:\n\"{pack.incident}\"\n\n"
            f"Evidence available up to that time:\n{pack.as_prompt_text()}\n\n"
            "Investigate and answer in the JSON format.")


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("The model did not return JSON.")
    return json.loads(match.group(0))


def check_citations(answer: dict, pack: EvidencePack) -> list[str]:
    """Return evidence IDs and ticket numbers the model mentioned that are not in the evidence."""
    text = json.dumps(answer)
    known_ids = {e.id for e in pack.items}
    bad_ids = sorted(set(re.findall(r"\bE\d+\b", text)) - known_ids, key=lambda x: int(x[1:]))
    known_tickets = set(re.findall(r"INC-\d{4}", " ".join(e.summary for e in pack.items)))
    bad_tickets = sorted(set(re.findall(r"INC-\d{4}", text)) - known_tickets)
    return bad_ids + bad_tickets


def investigate(pack: EvidencePack, client=None) -> tuple[dict, dict]:
    """Call Claude on Bedrock. Returns (answer, usage) where usage has token counts and latency."""
    import boto3

    client = client or boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-north-1"))
    response = client.converse(
        modelId=os.environ.get("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6"),
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": build_prompt(pack)}]}],
        inferenceConfig={"maxTokens": 4000, "temperature": 0},
    )
    text = response["output"]["message"]["content"][0]["text"]
    answer = _parse(text)
    usage = {"input_tokens": response["usage"]["inputTokens"], "output_tokens": response["usage"]["outputTokens"],
             "latency_ms": response.get("metrics", {}).get("latencyMs")}
    return answer, usage

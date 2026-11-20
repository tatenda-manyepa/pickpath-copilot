"""Accuracy check: runs every planted test incident through PickPath and scores the answers.

TEST-01 to TEST-05 have a known root cause. TEST-06 and TEST-07 are honesty tests: a new bug with no
history, and an incident the data does not cover. They pass only if the copilot invents nothing.

Run from the project folder:  python eval/run_eval.py
Writes the results to eval/results.md and the answers to eval/saved_answers.json (used by the public demo).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.ai import check_citations, investigate  # noqa: E402
from copilot.evidence import gather  # noqa: E402

# Words the likely cause must contain to count as correct (any one from each group)
EXPECTED = {
    "TEST-01": [["C2"], ["C4", "maintenance"]],
    "TEST-02": [["R07"], ["A04", "aisle"]],
    "TEST-03": [["slotting", "location", "WCS-402", "SLT-8841"]],
    "TEST-04": [["R31"], ["restart", "charge request", "fleet manager"]],
    "TEST-05": [["M2", "merge"]],
    "TEST-06": [["still executing", "busy", "rejected", "re-queue", "requeue", "allocator", "timeout"]],
    "TEST-07": [],
}


def ticket_of(answer: dict) -> str:
    """The similar ticket the answer claims, or '' if it says there is none."""
    t = (answer.get("similar_incident") or {}).get("ticket", "") or ""
    m = re.search(r"INC-\d{4}", t)
    return "" if not m or m.group(0) == "INC-0000" else m.group(0)


def honest(case: dict, answer: dict, bad: list[str]) -> bool:
    """Honesty test: nothing invented, no false 'similar past incident', and (if there is
    nothing to go on) the copilot says the evidence is not enough."""
    if bad or ticket_of(answer):
        return False
    if case["id"] == "TEST-07":
        return answer.get("status") == "insufficient_evidence"
    return answer.get("confidence", "").lower() != "high"


def score(case: dict, answer: dict) -> tuple[bool, bool, bool]:
    text = (answer.get("likely_cause", "") + " " + answer.get("reasoning", "")).lower()
    cause_ok = all(any(w.lower() in text for w in group) for group in EXPECTED[case["id"]])
    if case.get("honesty_test"):
        return cause_ok, not ticket_of(answer), (answer.get("runbook") or {}).get("id", "") in ("", "none", "RB-00")
    ticket_ok = ticket_of(answer) in (
        case["expected_similar_ticket"], *(["INC-0131"] if case["id"] == "TEST-03" else []),
        *(["INC-0125", "INC-0134"] if case["id"] == "TEST-05" else []))
    runbook_ok = (answer.get("runbook") or {}).get("id", "") == case["expected_runbook"]
    return cause_ok, ticket_ok, runbook_ok


def main() -> None:
    cases = json.load(open(ROOT / "eval" / "test_incidents.json"))
    rows, saved = [], {}
    known = honest_ok = known_total = honest_total = 0
    for case in cases:
        pack = gather(case["engineer_report"], datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M"))
        answer, usage = investigate(pack)
        cause_ok, ticket_ok, runbook_ok = score(case, answer)
        bad = check_citations(answer, pack)
        if case.get("honesty_test"):
            ok = honest(case, answer, bad) and cause_ok
            honest_total += 1
            honest_ok += ok
        else:
            ok = cause_ok
            known_total += 1
            known += ok
        saved[case["id"]] = {"recorded": f"{datetime.now():%d %b %Y}", "answer": answer, "usage": usage}
        rows.append(f"| {case['id']} | {case['label']} | {'✅' if ok else '❌'} | {'✅' if ticket_ok else '❌'} "
                    f"| {'✅' if runbook_ok else '❌'} | {'none' if not bad else ', '.join(bad)} "
                    f"| {answer.get('status', '')} | {answer.get('confidence', '')} | {answer.get('likely_cause', '')} |")
        print(f"{case['id']}: {'PASS' if ok else 'FAIL'} · {answer.get('status', '')} · {answer.get('confidence', '')} "
              f"· {answer.get('likely_cause', '')}")
    report = [f"# PickPath accuracy check ({datetime.now():%d %b %Y %H:%M})", "",
              f"**Correct root cause: {known} of {known_total} known incidents**  ",
              f"**Honest on unknown incidents: {honest_ok} of {honest_total}** (nothing invented, no false match, "
              "says when the evidence is not enough)", "",
              "| Test | Incident | Pass | Similar ticket | Runbook | Invalid citations | Status | Confidence | Likely cause |",
              "|---|---|---|---|---|---|---|---|---|", *rows]
    (ROOT / "eval" / "results.md").write_text("\n".join(report) + "\n")
    # Saved answers power the public demo's example incidents (no live AI call needed)
    (ROOT / "eval" / "saved_answers.json").write_text(json.dumps(saved, indent=2))
    print(f"\nCorrect root cause: {known} of {known_total}. Honest on unknowns: {honest_ok} of {honest_total}. "
          f"Passed {known + honest_ok} of {len(cases)}. Saved eval/results.md")


if __name__ == "__main__":
    main()

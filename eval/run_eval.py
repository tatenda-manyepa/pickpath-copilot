"""Accuracy check: runs every planted test incident through PickPath and scores the answers.

Run from the project folder:  python eval/run_eval.py
Writes the results to eval/results.md.
"""
from __future__ import annotations

import json
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
}


def score(case: dict, answer: dict) -> tuple[bool, bool, bool]:
    text = (answer.get("likely_cause", "") + " " + answer.get("reasoning", "")).lower()
    cause_ok = all(any(w.lower() in text for w in group) for group in EXPECTED[case["id"]])
    ticket_ok = (answer.get("similar_incident") or {}).get("ticket", "") in (
        case["expected_similar_ticket"], *(["INC-0131"] if case["id"] == "TEST-03" else []),
        *(["INC-0125", "INC-0134"] if case["id"] == "TEST-05" else []))
    runbook_ok = (answer.get("runbook") or {}).get("id", "") == case["expected_runbook"]
    return cause_ok, ticket_ok, runbook_ok


def main() -> None:
    cases = json.load(open(ROOT / "eval" / "test_incidents.json"))
    rows, correct = [], 0
    for case in cases:
        pack = gather(case["engineer_report"], datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M"))
        answer, usage = investigate(pack)
        cause_ok, ticket_ok, runbook_ok = score(case, answer)
        bad = check_citations(answer, pack)
        correct += cause_ok
        rows.append(f"| {case['id']} | {case['label']} | {'✅' if cause_ok else '❌'} | {'✅' if ticket_ok else '❌'} "
                    f"| {'✅' if runbook_ok else '❌'} | {'none' if not bad else ', '.join(bad)} "
                    f"| {answer.get('confidence', '')} | {answer.get('likely_cause', '')} |")
        print(f"{case['id']}: cause {'OK' if cause_ok else 'MISS'} · {answer.get('likely_cause', '')}")
    report = [f"# PickPath accuracy check ({datetime.now():%d %b %Y %H:%M})", "",
              f"**Correct root cause: {correct} of {len(cases)}**", "",
              "| Test | Incident | Cause | Similar ticket | Runbook | Invalid citations | Confidence | Likely cause |",
              "|---|---|---|---|---|---|---|---|", *rows]
    (ROOT / "eval" / "results.md").write_text("\n".join(report) + "\n")
    print(f"\nCorrect root cause: {correct} of {len(cases)}. Saved eval/results.md")


if __name__ == "__main__":
    main()

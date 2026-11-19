"""PickPath Copilot: Streamlit app.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import date, datetime, time as dtime
from pathlib import Path

import streamlit as st

from copilot.ai import check_citations, investigate
from copilot.evidence import gather

ROOT = Path(__file__).resolve().parent
LOG_FILE = ROOT / "logs" / "decisions.csv"
EXAMPLES = json.load(open(ROOT / "eval" / "test_incidents.json"))
DEFAULT = EXAMPLES[0]
SAVED_FILE = ROOT / "eval" / "saved_answers.json"
SAVED = json.load(open(SAVED_FILE)) if SAVED_FILE.exists() else {}
USAGE_FILE = ROOT / "logs" / "live_runs.csv"
# Public demo settings: live AI calls need this code and are capped per day.
# Leave DEMO_ACCESS_CODE unset (e.g. in Codespaces) to allow live runs without a code.
ACCESS_CODE = os.environ.get("DEMO_ACCESS_CODE", "")
DAILY_LIMIT = int(os.environ.get("DEMO_DAILY_LIMIT", "25"))


def matching_example(text: str, when: datetime):
    for case in EXAMPLES:
        if (case["engineer_report"].strip() == text.strip()
                and datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M") == when and case["id"] in SAVED):
            return case
    return None


def live_runs_today() -> int:
    if not USAGE_FILE.exists():
        return 0
    today = date.today().isoformat()
    return sum(1 for line in open(USAGE_FILE) if line.startswith(today))


def record_live_run() -> None:
    USAGE_FILE.parent.mkdir(exist_ok=True)
    with open(USAGE_FILE, "a") as f:
        f.write(f"{datetime.now().isoformat()}\n")

st.set_page_config(page_title="PickPath Copilot", page_icon="🛰️", layout="wide")

# ------------------------------------------------------------------ state
if "incident" not in st.session_state:
    st.session_state.incident = DEFAULT["engineer_report"]
    as_of = datetime.strptime(DEFAULT["as_of"], "%Y-%m-%d %H:%M")
    st.session_state.as_of_date, st.session_state.as_of_time = as_of.date(), as_of.time()


def load_example():
    label = st.session_state.example
    case = next((c for c in EXAMPLES if f"{c['id']} · {c['label']}" == label), None)
    if case:
        as_of = datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M")
        st.session_state.incident = case["engineer_report"]
        st.session_state.as_of_date, st.session_state.as_of_time = as_of.date(), as_of.time()
        st.session_state.pop("result", None)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### Northgate Fulfilment")
    st.caption("Fictional 24/7 distribution centre · 40 robots · 6 pick stations · 4 chargers")
    st.selectbox("Load an example incident", [f"{c['id']} · {c['label']}" for c in EXAMPLES],
                 key="example", on_change=load_example, index=None, placeholder="Choose an example")
    st.markdown("**Incident reported at**")
    st.date_input("Date", key="as_of_date", min_value=date(2026, 11, 10), max_value=date(2026, 11, 11))
    st.time_input("Time", key="as_of_time", step=60)
    st.caption("The copilot only reads records from before this time, so it cannot see how the incident was fixed.")
    st.divider()
    st.markdown("**Live AI investigation**")
    if ACCESS_CODE:
        st.caption("The example incidents show Claude’s saved answers. To run your own incident live, "
                   "enter the access code from my CV or message.")
        st.text_input("Access code", key="code", type="password")
    else:
        st.caption("Live mode: every investigation calls Claude on Amazon Bedrock.")
    st.divider()
    st.markdown(":orange[**Read-only by design**]")
    st.caption("PickPath can read telemetry, logs, tickets and runbooks. It cannot send any command to robots, "
               "chargers, conveyors or control systems. An engineer decides and acts.")
    st.caption("Model: Claude on Amazon Bedrock (EU inference profile)")

# ------------------------------------------------------------------ header and input
st.markdown("## PickPath Copilot")
st.caption("AI incident investigation for an automated warehouse · every answer cites its evidence · an engineer approves")

incident = st.text_area("What are you seeing?", key="incident", height=90,
                        placeholder="Example: Pick station 3 has been idle for 12 minutes. Operators are waiting for totes.")
as_of = datetime.combine(st.session_state.as_of_date, st.session_state.as_of_time)

if st.button("Investigate", type="primary", disabled=not incident.strip()):
    example = matching_example(incident, as_of)
    live_ok = (not ACCESS_CODE) or st.session_state.get("code", "") == ACCESS_CODE
    if not example and not live_ok:
        st.info("This incident is not one of the examples, so it needs a live AI call. Enter the access code in "
                "the sidebar, or choose an example incident to see Claude’s saved answer.")
        st.stop()
    if not example and ACCESS_CODE and live_runs_today() >= DAILY_LIMIT:
        st.warning("Today’s live investigations are used up. Please try an example incident, or come back tomorrow.")
        st.stop()
    with st.status("Investigating…", expanded=True) as status:
        st.write(f"Gathering evidence recorded up to {as_of:%H:%M on %a %d %b}…")
        pack = gather(incident, as_of)
        counts = {}
        for e in pack.items:
            counts[e.source] = counts.get(e.source, 0) + 1
        st.write("Found " + ", ".join(f"{n} {s}" for s, n in counts.items()) + ".")
        if example:
            saved = SAVED[example["id"]]
            st.write(f"Loading Claude’s saved answer for this example (recorded {saved['recorded']})…")
            answer, usage = saved["answer"], dict(saved.get("usage") or {})
            usage["seconds"] = round((usage.get("latency_ms") or 15000) / 1000, 1)
            usage["source"] = f"Saved answer from Claude on Amazon Bedrock, recorded {saved['recorded']}"
        else:
            st.write("Asking Claude on Amazon Bedrock to explain the likely cause…")
            started = time.time()
            try:
                answer, usage = investigate(pack)
            except Exception as exc:  # show a clear message instead of a stack trace
                status.update(label="The AI could not be reached", state="error")
                st.error(f"{type(exc).__name__}: {exc}")
                st.stop()
            if ACCESS_CODE:
                record_live_run()
            usage["seconds"] = round(time.time() - started, 1)
            usage["source"] = "Live answer from Claude on Amazon Bedrock"
        st.session_state.result = {"pack": pack, "answer": answer, "usage": usage, "logged": None}
        status.update(label="Investigation complete", state="complete", expanded=False)

# ------------------------------------------------------------------ results
result = st.session_state.get("result")
if result:
    pack, answer, usage = result["pack"], result["answer"], result["usage"]
    evidence = {e.id: e for e in pack.items}
    bad_ids = check_citations(answer, pack)
    st.caption(usage.get("source", ""))

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            if answer.get("status") == "insufficient_evidence":
                st.markdown(":orange[**Not enough evidence for a recommendation**]")
            else:
                st.markdown(":orange[**Likely cause**]")
            st.markdown(f"#### {answer.get('likely_cause', '')}")
            st.write(answer.get("reasoning", ""))
            conf = answer.get("confidence", "").lower()
            colour = {"high": "green", "medium": "orange", "low": "red"}.get(conf, "gray")
            st.markdown(f"Confidence: :{colour}[**{conf or 'unknown'}**]")
        if bad_ids:
            st.warning("Check before trusting: the answer mentions " + ", ".join(bad_ids)
                       + ", which is not in the evidence it was given. Treat that part with caution.")

        st.markdown("#### Evidence behind this")
        for item in answer.get("evidence", []):
            ev = evidence.get(item.get("id"))
            if not ev:
                continue
            with st.expander(f"**{ev.id}** · {item.get('why', '')}"):
                st.caption(ev.source)
                st.code(ev.detail or ev.summary, language=None, wrap_lines=True)

        if answer.get("ruled_out"):
            st.markdown("#### Ruled out")
            for r in answer["ruled_out"]:
                ids = ", ".join(r.get("ids", []))
                st.markdown(f"- **{r.get('what', '')}**: {r.get('why', '')}" + (f" ({ids})" if ids else ""))

    with right:
        m1, m2, m3 = st.columns(3)
        m1.metric("Records reviewed", len(pack.items))
        m2.metric("Cited", len(answer.get("evidence", [])))
        m3.metric("Answer time", f"{usage['seconds']} s")

        with st.container(border=True):
            st.markdown(":orange[**Try this first**]")
            rb = answer.get("runbook", {}) or {}
            st.markdown(f"**{rb.get('id') or 'No runbook'}**: {rb.get('next_step', '')}")
            sim = answer.get("similar_incident", {}) or {}
            if sim.get("ticket"):
                st.markdown(f"**Similar past incident: {sim['ticket']}**. {sim.get('why', '')}")
        if answer.get("check_next"):
            st.markdown("**Confirm before acting**")
            for c in answer["check_next"]:
                st.markdown(f"- {c}")
        if answer.get("prevention"):
            st.markdown("**Stop it recurring**")
            st.write(answer["prevention"])

        st.divider()
        st.markdown("#### Engineer decision")
        st.caption("Nothing happens on site until an engineer acts. Your decision is logged for review.")
        note = st.text_input("Note (optional)", key="decision_note")
        a, r = st.columns(2)
        decision = None
        if a.button("Approve", type="primary", use_container_width=True, disabled=bool(result["logged"])):
            decision = "approved"
        if r.button("Reject", use_container_width=True, disabled=bool(result["logged"])):
            decision = "rejected"
        if decision:
            LOG_FILE.parent.mkdir(exist_ok=True)
            new = not LOG_FILE.exists()
            with open(LOG_FILE, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["logged_at", "incident_time", "incident", "likely_cause", "confidence",
                                "cited_evidence", "decision", "note"])
                w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{as_of:%Y-%m-%d %H:%M}", incident,
                            answer.get("likely_cause", ""), answer.get("confidence", ""),
                            " ".join(i.get("id", "") for i in answer.get("evidence", [])), decision, note])
            result["logged"] = decision
            st.rerun()
        if result["logged"]:
            st.success(f"Recommendation {result['logged']} and logged.")

    with st.expander(f"All evidence gathered ({len(pack.items)} records)"):
        for e in pack.items:
            st.markdown(f"**{e.id}** · _{e.source}_ · {e.summary}")

if LOG_FILE.exists():
    with st.expander("Decision log"):
        rows = list(csv.DictReader(open(LOG_FILE)))
        st.dataframe(rows[::-1], use_container_width=True, hide_index=True)

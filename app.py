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
# Labels describe the symptom only, so visitors watch the copilot find the cause
SYMPTOM = {"TEST-01": "Pick station 3 idle", "TEST-02": "Robot stuck in an aisle",
           "TEST-03": "Errors on stations 4 and 6", "TEST-04": "Robot stopped in a lane",
           "TEST-05": "Station 5 can't send totes"}


def example_label(case: dict) -> str:
    return SYMPTOM.get(case["id"], case["label"])
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
def use_example(case: dict):
    st.session_state.incident = case["engineer_report"]
    st.session_state.as_of = datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M")
    st.session_state.active = case["id"]
    st.session_state.pop("result", None)
    st.session_state.auto_run = True


def use_own_incident():
    st.session_state.incident = st.session_state.own_text.strip()
    st.session_state.as_of = datetime.combine(st.session_state.own_date, st.session_state.own_time)
    st.session_state.active = None
    st.session_state.pop("result", None)
    st.session_state.auto_run = True


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### Northgate Fulfilment")
    st.caption("A fictional 24/7 distribution centre with 40 robots, 6 pick stations and 4 chargers. "
               "All data is invented.")
    st.markdown(":orange[**Read-only by design**]")
    st.caption("PickPath reads telemetry, logs, past tickets and runbooks. It cannot send any command to robots, "
               "chargers, conveyors or control systems. An engineer decides and acts.")
    st.caption("It only reads records from before an incident was reported, so it cannot see how it was fixed.")
    st.caption("Model: Claude on Amazon Bedrock (EU inference profile)")
    if ACCESS_CODE:
        st.divider()
        with st.expander("Have an access code?"):
            st.caption("Enter the code from my message to describe your own incident and get a live answer.")
            st.text_input("Access code", key="code", type="password")
live_allowed = (not ACCESS_CODE) or st.session_state.get("code", "") == ACCESS_CODE

# ------------------------------------------------------------------ header and instructions
st.markdown("## PickPath Copilot")
st.caption("AI incident investigation for an automated warehouse · every answer cites its evidence · an engineer approves")

with st.container(border=True):
    st.markdown("**How to try it**")
    st.markdown("**1.** Click an incident below. Start with **Pick station 3 idle**.  \n"
                "**2.** Read the likely cause, the evidence behind it and what it ruled out.  \n"
                "**3.** Approve or reject the recommendation, as the on-call engineer would.")
    st.caption("Only two of these incidents really need AI. For the others, watch whether the copilot says a "
               "simple rule, an alert or a maintenance fix is the better answer.")

active = st.session_state.get("active")
cols = st.columns(len(EXAMPLES))
for col, case in zip(cols, EXAMPLES):
    col.button(example_label(case), key=f"ex_{case['id']}", use_container_width=True,
               type="primary" if case["id"] == active else "secondary",
               on_click=use_example, args=(case,))

if live_allowed and ACCESS_CODE:
    with st.expander("Or describe your own incident (live AI)", expanded=False):
        st.text_area("What is the engineer seeing?", key="own_text", height=80,
                     placeholder="Example: Robots in group G2 keep stopping near pick station 2.")
        c1, c2 = st.columns(2)
        c1.date_input("Reported on", key="own_date", value=date(2026, 11, 11),
                      min_value=date(2026, 11, 10), max_value=date(2026, 11, 11))
        c2.time_input("At", key="own_time", value=dtime(14, 21), step=60)
        st.button("Investigate my incident", on_click=use_own_incident,
                  disabled=not st.session_state.get("own_text", "").strip())

incident = st.session_state.get("incident")
as_of = st.session_state.get("as_of")
if not incident:
    st.info("Click an incident above to start.")
    st.stop()

with st.container(border=True):
    st.caption(f"Engineer reports · {as_of:%a %d %b %Y, %H:%M}")
    st.markdown(f"**“{incident}”**")

if st.session_state.pop("auto_run", False):
    example = matching_example(incident, as_of)
    if not example and not live_allowed:
        st.info("Live investigations need an access code.")
        st.stop()
    if not example and ACCESS_CODE and live_runs_today() >= DAILY_LIMIT:
        st.warning("Today’s live investigations are used up. Please try one of the example incidents.")
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
                st.markdown(":orange[**Step 2 · Likely cause**]")
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
        st.markdown("#### Step 3: your decision")
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

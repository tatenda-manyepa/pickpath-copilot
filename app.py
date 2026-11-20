"""PickPath Copilot: Streamlit app.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import csv
import html
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
           "TEST-05": "Station 5 can't send totes", "TEST-06": "Station 6 slow, totes in bursts",
           "TEST-07": "Wrong images on station 2"}


# Open tickets on the shift, numbered after the historical tickets (INC-0125 to INC-0144), in time order
TICKET = {"TEST-02": "INC-0145", "TEST-03": "INC-0146", "TEST-04": "INC-0147", "TEST-05": "INC-0148",
          "TEST-01": "INC-0149", "TEST-06": "INC-0150", "TEST-07": "INC-0151"}
CONTACT = "mailto:t.manyepa@outlook.com?subject=PickPath%20Copilot%20access%20code"
ASK_FOR_CODE = ("The open tickets replay real answers the AI gave earlier. To run the AI live on your own "
                f"incident description, [email me for an access code]({CONTACT}).")
POINT_TO_SIDEBAR = ("New incident descriptions run the AI live. See “Want to try your own incident?” in the sidebar, "
                    "or pick one of the open tickets.")


def example_label(case: dict) -> str:
    return SYMPTOM.get(case["id"], case["label"])


def find_ticket(text: str):
    t = text.strip().upper().replace(" ", "")
    if t.isdigit():
        t = f"INC-{int(t):04d}"
    return next((c for c in EXAMPLES if TICKET.get(c["id"]) == t), None)
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


CONSOLE_CSS = """<style>
.pp-console{background:#0D1626;border:1px solid #31446A;border-radius:12px;margin:6px 0 14px;overflow:hidden;
 font:400 14px/1.7 "JetBrains Mono",ui-monospace,Consolas,monospace;box-shadow:0 18px 40px #0006}
.pp-bar{display:flex;align-items:center;gap:6px;padding:8px 12px;border-bottom:1px solid #23334F;color:#7787A3;font-size:12px}
.pp-bar i{width:9px;height:9px;border-radius:50%;background:#31446A;display:inline-block}.pp-bar i:first-child{background:#FF7A6B}
.pp-bar span{margin-left:auto}.pp-body{padding:10px 14px;min-height:60px}.pp-body p{margin:0;white-space:pre-wrap;color:#E9EEF6}
.pp-cmd{color:#FFB547!important}.pp-dim{color:#7787A3!important}.pp-ok{color:#4FD1A5!important}.pp-warn{color:#FFB547!important}
.pp-err{color:#FF7A6B!important}.pp-caret::after{content:"▍";color:#FFB547;animation:ppblink 1s steps(1) infinite}
@keyframes ppblink{50%{opacity:0}}
</style>"""


def render_console(lines, typing: bool = False) -> str:
    rows = []
    for i, (kind, text) in enumerate(lines):
        cls = f"pp-{kind}" if kind else ""
        if typing and i == len(lines) - 1:
            cls += " pp-caret"
        rows.append(f'<p class="{cls}">{html.escape(text)}</p>')
    return (CONSOLE_CSS + '<div class="pp-console"><div class="pp-bar"><i></i><i></i><i></i><span>pickpath-copilot</span></div>'
            f'<div class="pp-body">{"".join(rows)}</div></div>')


def record_live_run() -> None:
    USAGE_FILE.parent.mkdir(exist_ok=True)
    with open(USAGE_FILE, "a") as f:
        f.write(f"{datetime.now().isoformat()}\n")

st.set_page_config(page_title="PickPath Copilot", page_icon="🛰️", layout="wide")

# ------------------------------------------------------------------ state
def use_example(case: dict):
    st.session_state.incident = case["engineer_report"]
    st.session_state.as_of = datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M")
    st.session_state.ticket = TICKET.get(case["id"])
    st.session_state.active = case["id"]
    st.session_state.notice = None
    st.session_state.pop("result", None)
    st.session_state.auto_run = True


def submit_input():
    text = st.session_state.entry.strip()
    st.session_state.notice = None
    if not text:
        return
    case = find_ticket(text)
    if case:
        use_example(case)
        return
    if not live_allowed():
        st.session_state.notice = POINT_TO_SIDEBAR
        return
    st.session_state.incident = text
    st.session_state.as_of = datetime.combine(st.session_state.own_date, st.session_state.own_time)
    st.session_state.ticket = None
    st.session_state.active = None
    st.session_state.pop("result", None)
    st.session_state.auto_run = True


def live_allowed() -> bool:
    return (not ACCESS_CODE) or st.session_state.get("code", "") == ACCESS_CODE


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
        with st.expander("Want to try your own incident?"):
            st.caption(ASK_FOR_CODE)
            st.text_input("Access code", key="code", type="password")

# ------------------------------------------------------------------ header, instructions, input
st.markdown("## PickPath Copilot")
st.caption("AI incident investigation for an automated warehouse · every answer cites its evidence · an engineer approves")

with st.container(border=True):
    st.markdown("**How to try it**")
    st.markdown("**1.** Pick one of the shift’s open tickets below (start with **INC-0149**), or enter a ticket "
                "number or incident description, as an on-call engineer would.  \n"
                "**2.** Read the likely cause, the evidence behind it and what it ruled out.  \n"
                "**3.** Approve or reject the recommendation, or escalate it if you're not sure.")
    st.caption("Not every incident needs AI, and two are new problems with no history. Watch whether the copilot "
               "recommends a simple rule, an alert or a maintenance fix instead, and whether it admits when it "
               "doesn't know.")

st.markdown("""<style>
button[kind^="primary"] p{color:#2A1B00;font-weight:600}
.st-key-tickets button{background:#F4F6FA;color:#0E1A2E;border:1px solid #F4F6FA;font-weight:600}
.st-key-tickets button p{color:#0E1A2E}
.st-key-tickets button:hover{background:#FFFFFF;border-color:#FFB547;color:#0E1A2E}
.st-key-tickets button[kind="primary"]{background:#FFB547;border-color:#FFB547}
.st-key-tickets button[kind="primary"] p{color:#2A1B00}
</style>""", unsafe_allow_html=True)
st.markdown("**Open tickets this shift**")
active = st.session_state.get("active")
# Flagship demo first, then newest first. Tickets without a saved answer stay hidden in the public demo.
shown_cases = [c for c in EXAMPLES if c["id"] in SAVED or not ACCESS_CODE]
ordered = sorted(shown_cases, key=lambda c: (c["id"] != "TEST-01", [-ord(ch) for ch in TICKET.get(c["id"], "")]))
tickets = st.container(key="tickets")
for row in (ordered[i:i + 3] for i in range(0, len(ordered), 3)):
    cols = tickets.columns(3)
    for col, case in zip(cols, row):
        when = datetime.strptime(case["as_of"], "%Y-%m-%d %H:%M")
        col.button(f"{TICKET[case['id']]} · {example_label(case)} · {when:%a %H:%M}", key=f"ex_{case['id']}",
                   use_container_width=True, type="primary" if case["id"] == active else "secondary",
                   on_click=use_example, args=(case,))

with st.form("entry_form", border=False):
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    c1.text_input("Ticket number or incident description", key="entry",
                  placeholder="e.g. INC-0149, or: Robots near pick station 2 keep stopping")
    c2.form_submit_button("Investigate", type="primary", use_container_width=True, on_click=submit_input)
    with st.expander("Report time for a new incident description"):
        d1, d2 = st.columns(2)
        d1.date_input("Reported on", key="own_date", value=date(2026, 11, 11),
                      min_value=date(2026, 11, 10), max_value=date(2026, 11, 11))
        d2.time_input("At", key="own_time", value=dtime(14, 21), step=60)
if st.session_state.get("notice"):
    st.info(st.session_state.notice)

incident = st.session_state.get("incident")
as_of = st.session_state.get("as_of")
if not incident:
    st.stop()

with st.container(border=True):
    tk = st.session_state.get("ticket")
    st.caption((f"{tk} · " if tk else "New incident · ") + f"Engineer reports · {as_of:%a %d %b %Y, %H:%M}")
    st.markdown(f"**“{incident}”**")

if st.session_state.pop("auto_run", False):
    example = matching_example(incident, as_of)
    if not example and not live_allowed():
        st.info(POINT_TO_SIDEBAR)
        st.stop()
    if not example and ACCESS_CODE and live_runs_today() >= DAILY_LIMIT:
        st.warning("Today’s live investigations are used up. Please try one of the example incidents.")
        st.stop()
    console = st.empty()
    shown: list[tuple[str, str]] = []

    def type_line(kind: str, text: str, speed: int = 3):
        """Type one console line character by character, keeping earlier lines."""
        for i in range(0, len(text) + 1, speed):
            console.markdown(render_console(shown + [(kind, text[:i])], typing=True), unsafe_allow_html=True)
            time.sleep(0.012)
        shown.append((kind, text))
        console.markdown(render_console(shown, typing=True), unsafe_allow_html=True)
        time.sleep(0.15)

    short = incident if len(incident) <= 48 else incident[:47] + "…"
    type_line("cmd", f'$ incident "{short}"')
    type_line("dim", f"› gathering evidence recorded up to {as_of:%H:%M}…")
    pack = gather(incident, as_of)
    counts = {}
    for e in pack.items:
        counts[e.source] = counts.get(e.source, 0) + 1
    names = {"telemetry": ("robot reading", "robot readings"), "log": ("log event", "log events"),
             "stations": ("station report", "station reports"), "fault codes": ("fault code list", "fault code lists"),
             "ticket": ("past ticket", "past tickets"), "runbook": ("runbook", "runbooks")}
    type_line("", "› found " + ", ".join(f"{n} {names.get(s, (s, s))[n != 1]}" for s, n in counts.items()))
    if example:
        saved = SAVED[example["id"]]
        type_line("dim", "› loading Claude’s saved answer for this ticket…")
        answer, usage = saved["answer"], dict(saved.get("usage") or {})
        usage["seconds"] = round((usage.get("latency_ms") or 15000) / 1000, 1)
        usage["source"] = f"Saved answer from Claude on Amazon Bedrock, recorded {saved['recorded']}"
    else:
        type_line("dim", "› asking Claude on Amazon Bedrock…")
        started = time.time()
        try:
            answer, usage = investigate(pack)
        except Exception as exc:  # show a clear message instead of a stack trace
            type_line("err", "✗ the AI could not be reached")
            st.error(f"{type(exc).__name__}: {exc}")
            st.stop()
        if ACCESS_CODE:
            record_live_run()
        usage["seconds"] = round(time.time() - started, 1)
        usage["source"] = "Live answer from Claude on Amazon Bedrock"
    for item in (answer.get("evidence") or [])[:3]:
        type_line("", f"› {item.get('id', '')} {item.get('why', '')}")
    cause = answer.get("likely_cause", "")
    if answer.get("status") == "insufficient_evidence":
        type_line("warn", "! not enough evidence for a recommendation")
    else:
        type_line("ok", "✓ likely cause: " + (cause if len(cause) <= 90 else cause[:89] + "…"))
    type_line("warn", "⏸ awaiting engineer approval")
    console.markdown(render_console(shown), unsafe_allow_html=True)
    st.session_state.result = {"pack": pack, "answer": answer, "usage": usage, "logged": None, "console": shown}
    st.rerun()

# ------------------------------------------------------------------ results
result = st.session_state.get("result")
if result:
    pack, answer, usage = result["pack"], result["answer"], result["usage"]
    evidence = {e.id: e for e in pack.items}
    bad_ids = check_citations(answer, pack)
    if result.get("console"):
        st.markdown(render_console(result["console"]), unsafe_allow_html=True)
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
        st.caption("Human in the loop: nothing happens on site until an engineer acts. Check the answer against "
                   "what you see, then decide. Every decision is logged, so wrong answers can be reviewed and fixed.")
        note = st.text_input("Note (optional)", key="decision_note")
        a, r = st.columns(2)
        decision = None
        if a.button("Approve", type="primary", use_container_width=True, disabled=bool(result["logged"])):
            decision = "approved"
        if r.button("Reject", use_container_width=True, disabled=bool(result["logged"])):
            decision = "rejected"
        if st.button("Not sure: escalate to a senior engineer", use_container_width=True,
                     disabled=bool(result["logged"])):
            decision = "escalated"
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
            st.success({"approved": "Recommendation approved and logged.",
                        "rejected": "Recommendation rejected and logged for review.",
                        "escalated": "Escalated to a senior engineer, with the evidence attached, and logged."}
                       .get(result["logged"], "Decision logged."))

    with st.expander(f"All evidence gathered ({len(pack.items)} records)"):
        for e in pack.items:
            st.markdown(f"**{e.id}** · _{e.source}_ · {e.summary}")

if LOG_FILE.exists():
    with st.expander("Decision log"):
        rows = list(csv.DictReader(open(LOG_FILE)))
        st.dataframe(rows[::-1], use_container_width=True, hide_index=True)

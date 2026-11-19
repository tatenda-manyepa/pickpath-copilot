"""Evidence retrieval for PickPath Copilot.

Reads the fictional Northgate Fulfilment dataset and gathers the records that
matter for an incident. Only records at or before the incident's report time
(`as_of`) are used, so the copilot can never read how the incident was resolved.

Every piece of evidence gets an ID (E1, E2, ...) that the AI must cite.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
TS = "%Y-%m-%d %H:%M:%S"

NORMAL_STATES = {"MOVING", "DELIVERING", "AT_STATION", "IDLE", "CHARGING", "TO_CHARGE"}
ROUTINE_LOG = ("TASK_CREATE", "TASK_ASSIGN", "TASK_COMPLETE", "WAVE_RELEASE", "CHARGE_END")
STOPWORDS = set("""a an the and or of to in on at for is are was were be been has have had it its this that
with from by as not no but if then than into out up down over our we i you they he she them their there
been being do does did can could should would will just only also very after before about been minutes min
operators waiting has have""".split())


@dataclass
class Evidence:
    id: str
    source: str          # telemetry, log, stations, ticket, runbook
    summary: str         # one line the AI and the engineer read
    detail: str = ""     # raw records behind the summary


@dataclass
class EvidencePack:
    incident: str
    as_of: datetime
    items: list[Evidence] = field(default_factory=list)

    def add(self, source: str, summary: str, detail: str = "") -> Evidence:
        ev = Evidence(f"E{len(self.items) + 1}", source, summary, detail)
        self.items.append(ev)
        return ev

    def by_source(self, source: str) -> list[Evidence]:
        return [e for e in self.items if e.source == source]

    def as_prompt_text(self) -> str:
        lines = []
        for e in self.items:
            lines.append(f"[{e.id}] ({e.source}) {e.summary}")
            if e.detail and e.source in ("runbook", "ticket"):
                lines.append(_indent(e.detail))
        return "\n".join(lines)


def _indent(text: str) -> str:
    return "\n".join("    " + line for line in text.strip().splitlines())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower()) if w not in STOPWORDS and len(w) > 1}


# ------------------------------------------------------------------ loaders
_cache: dict[str, object] = {}


def _load(name: str, loader):
    if name not in _cache:
        _cache[name] = loader()
    return _cache[name]


def telemetry() -> list[dict]:
    def load():
        rows = list(csv.DictReader(open(DATA / "robot_telemetry.csv")))
        for r in rows:
            r["t"] = datetime.strptime(r["timestamp"], TS)
            r["battery"] = float(r["battery_pct"])
        return rows
    return _load("telemetry", load)


def log_lines() -> list[dict]:
    def load():
        out = []
        for line in open(DATA / "wcs_messages.log"):
            if line.startswith("#") or not line.strip():
                continue
            parts = [p.strip() for p in line.split("|", 5)]
            out.append({"t": datetime.strptime(parts[0][:19], TS), "level": parts[1], "source": parts[2],
                        "entity": parts[3], "code": "" if parts[4] == "-" else parts[4], "msg": parts[5],
                        "raw": line.rstrip()})
        return out
    return _load("log", load)


def stations() -> list[dict]:
    def load():
        rows = list(csv.DictReader(open(DATA / "pick_station_events.csv")))
        for r in rows:
            r["t"] = datetime.strptime(r["interval_start"], TS)
        return rows
    return _load("stations", load)


def tickets() -> list[dict]:
    return _load("tickets", lambda: json.load(open(DATA / "incident_tickets.json")))


def fault_codes() -> dict[str, dict]:
    return _load("codes", lambda: {r["code"]: r for r in csv.DictReader(open(DATA / "fault_codes.csv"))})


def runbooks() -> dict[str, str]:
    def load():
        return {p.name[:5]: p.read_text() for p in sorted((DATA / "runbooks").glob("RB-*.md"))}
    return _load("runbooks", load)


# ------------------------------------------------------------------ gatherers
ROBOT_STATION = {f"R{i:02d}": f"PS{(0 if i <= 7 else 1 if i <= 14 else 2 if i <= 21 else 3 if i <= 27 else 4 if i <= 34 else 5) + 1}"
                 for i in range(1, 41)}

def _stations_mentioned(text: str) -> list[str]:
    found = set()
    for group in re.findall(r"\b(?:ps|pick stations?|stations?)\s*((?:[1-6](?:\s*(?:,|and|&|/)\s*)?)+)", text.lower()):
        found |= set(re.findall(r"[1-6]", group))
    return sorted(f"PS{n}" for n in found)


def _robots_mentioned(text: str) -> list[str]:
    return sorted({f"R{int(n):02d}" for n in re.findall(r"\bR(\d{1,2})\b", text, flags=re.I)})


def _gather_telemetry(pack: EvidencePack, focus_stations: list[str], focus_robots: list[str]) -> set[str]:
    """Latest state of each robot, plus how long it has been in that state."""
    as_of = pack.as_of
    window = [r for r in telemetry() if as_of - timedelta(hours=2) <= r["t"] <= as_of]
    by_robot: dict[str, list[dict]] = {}
    for r in window:
        by_robot.setdefault(r["robot_id"], []).append(r)
    codes, abnormal, normal_count = set(), [], 0
    for robot, rows in sorted(by_robot.items()):
        rows.sort(key=lambda r: r["t"])
        latest = rows[-1]
        if as_of - latest["t"] > timedelta(minutes=75):
            continue
        state = latest["state"]
        relevant = (state not in NORMAL_STATES or latest["assigned_station"] in focus_stations
                    or robot in focus_robots)
        if not relevant:
            normal_count += 1
            continue
        since = latest["t"]
        for r in reversed(rows):
            if r["state"] != state:
                break
            since = r["t"]
        code = latest["fault_code"]
        if code:
            codes.add(code)
        abnormal.append((latest, since))
    for latest, since in abnormal:
        bits = [f"{latest['robot_id']} (group {latest['group']}, serves {latest['assigned_station']})",
                f"state {latest['state']}", f"zone {latest['zone']}", f"battery {latest['battery']:.1f}%"]
        if latest["fault_code"]:
            bits.append(f"fault {latest['fault_code']}")
        if latest["charger_id"]:
            bits.append(f"charger {latest['charger_id']}")
        if latest["state"] not in NORMAL_STATES:
            bits.append(f"in this state since {since:%H:%M}")
        pack.add("telemetry", f"{latest['t']:%H:%M} " + ", ".join(bits))
    if normal_count:
        pack.add("telemetry", f"{as_of:%H:%M} {normal_count} other robots reporting normal working states")
    return codes


def _gather_log(pack: EvidencePack, focus_stations: list[str], focus_robots: list[str]) -> set[str]:
    """Warnings, errors and notable events. Repeated messages are collapsed."""
    as_of = pack.as_of
    recent, codes = [], set()
    for line in log_lines():
        if line["t"] > as_of:
            break
        age = as_of - line["t"]
        long_lived = line["code"] == "CHG-250" or "planned maintenance" in line["msg"].lower()
        if age > timedelta(hours=14 if long_lived else 2):
            continue
        if line["code"] == "AMR-101" and (age > timedelta(minutes=45) or (
                ROBOT_STATION.get(line["entity"]) not in focus_stations and line["entity"] not in focus_robots)):
            continue
        if line["msg"].startswith(ROUTINE_LOG) or line["msg"].startswith("FLEET_STATUS"):
            continue
        if line["level"] == "INFO" and not line["code"] and line["source"] not in ("CONFIG",) and not any(
                k in line["msg"] for k in ("maintenance", "Slotting", "restart", "online", "resync", "Resent",
                                           "cleared", "stopped", "restarted", "mode", "Isolated", "Self-test")):
            continue
        recent.append(line)
    # collapse repeats of the same code and entity
    groups: dict[tuple, list[dict]] = {}
    order = []
    for line in recent:
        key = (line["code"], line["entity"]) if line["code"] in ("WCS-402", "WCS-430", "AMR-101") else id(line)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(line)
    for key in order:
        lines = groups[key]
        first = lines[0]
        if first["code"]:
            codes.add(first["code"])
        if len(lines) == 1:
            pack.add("log", f"{first['t']:%H:%M:%S} {first['level']} {first['source']} {first['entity']} "
                            f"{first['code'] or ''} {first['msg']}".replace("  ", " "), first["raw"])
        else:
            last = lines[-1]
            pack.add("log", f"{first['t']:%H:%M}-{last['t']:%H:%M} {first['source']} {first['code']} repeated "
                            f"{len(lines)} times for {first['entity']}. Latest: {last['msg']}",
                     "\n".join(l["raw"] for l in lines))
    return codes


def _gather_stations(pack: EvidencePack, focus_stations: list[str]) -> None:
    as_of = pack.as_of
    # Only completed 15-minute intervals, so nothing after the report time leaks in
    rows = [r for r in stations() if as_of - timedelta(minutes=75) <= r["t"] and r["t"] + timedelta(minutes=15) <= as_of]
    targets = focus_stations or sorted({r["station_id"] for r in rows})
    for st in targets:
        mine = [r for r in rows if r["station_id"] == st]
        if not mine:
            continue
        parts = [f"{r['t']:%H:%M} totes {r['totes_arrived']}, picks/h {r['picks_per_hour']}, idle {r['idle_minutes']} min"
                 + (f", last tote {r['last_tote_arrival']}" if r["last_tote_arrival"] else "")
                 + (f", operator logged in {r['operator_logged_in']}")
                 + (f", note: {r['note']}" if r["note"] else "") for r in mine]
        pack.add("stations", f"{st} 15-minute intervals: " + "; ".join(parts))
    if focus_stations:
        others = [r for r in rows if r["station_id"] not in focus_stations and r["t"] == max(x["t"] for x in rows)]
        if others:
            pack.add("stations", f"Other stations at {others[0]['t']:%H:%M}: " + "; ".join(
                f"{r['station_id']} {r['picks_per_hour']} picks/h" for r in others))


def _gather_tickets(pack: EvidencePack, codes: set[str], focus_stations: list[str]) -> None:
    """Past tickets similar by symptom or by fault code. Includes look-alikes on purpose,
    so the AI has to judge which past incident really matches."""
    words = _tokens(pack.incident)
    stations_txt = {s.lower() for s in focus_stations}
    scored = []
    for t in tickets():
        if datetime.strptime(t["opened"], "%Y-%m-%d %H:%M") > pack.as_of:
            continue
        symptom = _tokens(t["reported_symptom"]) | _tokens(" ".join(t["components"]))
        station_hit = any(s in t["reported_symptom"].lower().replace("pick station ", "ps") for s in stations_txt)
        by_symptom = len(words & symptom) + (3 if station_hit else 0)
        by_code = len(codes & set(t["fault_codes"]))
        scored.append((by_symptom, by_code, t))
    picks = []
    for key in (lambda x: x[0] * 2 + x[1] * 3, lambda x: x[0], lambda x: x[1]):
        for item in sorted(scored, key=lambda x: -key(x)):
            if key(item) > 0 and item[2] not in picks:
                picks.append(item[2])
                break
    for item in sorted(scored, key=lambda x: -(x[0] * 2 + x[1] * 3)):
        if len(picks) >= 3:
            break
        if item[2] not in picks and item[0] + item[1] > 0:
            picks.append(item[2])
    for t in picks:
        detail = (f"Symptom: {t['reported_symptom']}\nInvestigation: {t['investigation_notes']}\n"
                  f"Root cause: {t['root_cause']}\nFix: {t['fix']}\nRunbook: {t['runbook'] or 'none'}; "
                  f"time to resolve {t['time_to_resolve_min']} min")
        pack.add("ticket", f"{t['ticket_id']} ({t['opened'][:10]}): {t['reported_symptom']} Fault codes: "
                           f"{', '.join(t['fault_codes']) or 'none'}", detail)


def _gather_runbooks(pack: EvidencePack, codes: set[str]) -> None:
    fc = fault_codes()
    ids = []
    rank = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}
    for code in sorted(codes, key=lambda c: (rank.get(fc.get(c, {}).get("severity"), 9), c)):
        rb = fc.get(code, {}).get("runbook")
        if rb and rb not in ids:
            ids.append(rb)
    for t in pack.by_source("ticket"):
        m = re.search(r"Runbook: (RB-\d\d)", t.detail)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    books = runbooks()
    for rb in ids[:3]:
        if rb in books:
            title = books[rb].splitlines()[0].lstrip("# ")
            pack.add("runbook", title, books[rb])


def _gather_codes(pack: EvidencePack, codes: set[str]) -> None:
    fc = fault_codes()
    known = [fc[c] for c in sorted(codes) if c in fc]
    if known:
        pack.add("fault codes", "; ".join(f"{c['code']} = {c['description']} ({c['component']}, {c['severity']})"
                                          for c in known))


def gather(incident: str, as_of: datetime) -> EvidencePack:
    """Collect all evidence for an incident reported at `as_of`."""
    pack = EvidencePack(incident=incident, as_of=as_of)
    focus_stations = _stations_mentioned(incident)
    focus_robots = _robots_mentioned(incident)
    codes = _gather_telemetry(pack, focus_stations, focus_robots)
    codes |= _gather_log(pack, focus_stations, focus_robots)
    _gather_stations(pack, focus_stations)
    _gather_codes(pack, codes)
    _gather_tickets(pack, codes, focus_stations)
    _gather_runbooks(pack, codes)
    return pack

"""Generate the fictional Northgate Fulfilment dataset for PickPath Copilot.

Produces robot_telemetry.csv, wcs_messages.log and pick_station_events.csv in ../data.
Everything is invented. Deterministic: same output every run.

Site model
- 40 AMRs (R01-R40) in 6 groups; group Gn serves pick station PSn.
- 4 chargers: C1, C3 (CHG-WEST) and C2, C4 (CHG-EAST).
- Affinity: G1, G2, G5, G6 -> west; G3, G4 -> east. No automatic failover.
- Robots seek charge at 15%, stop at 10% (AMR-112), charge to 90% at 2.5%/min.

Planted incidents (times are local, Europe/London = UTC in November)
  A  Tue 10 Nov 09:41  R07 safety stop in aisle A04, R03/R05 blocked        -> blocked aisle
  B  Tue 10 Nov 16:15  WMS slotting update -> burst of WCS-402 rejects        -> message rejects
  C  Wed 11 Nov 05:41  fleet manager restart loses R31 charge request         -> low battery
  D  Wed 11 Nov 11:12  repeated jam at conveyor merge M2, PS5 outbound full   -> conveyor jam
  E  Wed 11 Nov 14:02  charger C2 contactor fault while C4 in maintenance;
                       G3 robots queue, PS3 starved (the DEMO incident)       -> charger failure
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data"
BASE = datetime(2026, 11, 10, 0, 0)
MINUTES = 2 * 24 * 60
D2 = 1440  # minute offset of day 2 (Wed 11 Nov)


def hm(day, h, m):
    return (D2 if day == 2 else 0) + h * 60 + m


def ts(t, sec=0):
    return (BASE + timedelta(minutes=t, seconds=sec)).strftime("%Y-%m-%d %H:%M:%S")


ROBOTS = [f"R{i:02d}" for i in range(1, 41)]
GROUP_RANGES = {"G1": (1, 7), "G2": (8, 14), "G3": (15, 21), "G4": (22, 27), "G5": (28, 34), "G6": (35, 40)}
GROUP = {f"R{i:02d}": g for g, (a, b) in GROUP_RANGES.items() for i in range(a, b + 1)}
STATION = {g: f"PS{g[1]}" for g in GROUP_RANGES}
WEST, EAST = ["C1", "C3"], ["C2", "C4"]
CHG_ZONE = {"west": "CHG-WEST", "east": "CHG-EAST"}

SEEK, CRIT, FULL, CHG_RATE = 15.0, 10.0, 90.0, 2.5

# Charger outages: (charger, start, end, code)
OUTAGES = [
    ("C4", hm(2, 12, 30), hm(2, 17, 30), "CHG-250"),  # planned firmware upgrade
    ("C2", hm(2, 14, 2), hm(2, 14, 41), "CHG-214"),   # demo fault, cleared by power-cycle
]
REROUTE_G3 = (hm(2, 14, 34), hm(2, 16, 0))  # engineer changes G3 affinity to west, then restores
G3_ANY = (hm(2, 14, 45), hm(2, 16, 0))  # C2 added back to G3 affinity once it passes self-test

# Forced robot states: robot -> list of (start, end, state, zone, code)
OVERRIDES = {
    "R07": [(hm(1, 9, 41), hm(1, 10, 5), "FAULT", "A04", "AMR-305")],
    "R03": [(hm(1, 9, 43), hm(1, 10, 5), "BLOCKED", "A04", "AMR-207")],
    "R05": [(hm(1, 9, 46), hm(1, 10, 5), "BLOCKED", "A04", "AMR-207")],
    "R17": [(hm(2, 14, 10), hm(2, 14, 38), "BLOCKED", "CHG-CORR-E", "AMR-207")],
    "R20": [(hm(2, 14, 11), hm(2, 14, 38), "BLOCKED", "CHG-CORR-E", "AMR-207")],
}

# Seek-charge timing targets used to tune starting batteries
TARGETS = {"R18": hm(2, 13, 59), "R15": hm(2, 14, 0), "R16": hm(2, 14, 2),
           "R19": hm(2, 14, 4), "R21": hm(2, 14, 6), "R31": hm(2, 5, 42)}
AVOID = {r: (hm(2, 13, 15), hm(2, 14, 55)) for r in ["R17", "R20", "R22", "R23", "R24", "R25", "R26", "R27"]}
AVOID.update({r: (hm(1, 9, 20), hm(1, 10, 15)) for r in ["R03", "R05", "R07"]})
R31_LOST = (hm(2, 5, 35), hm(2, 5, 50))  # charge request in this window is lost (fleet manager restart)
R31_TOW = hm(2, 6, 52)


def charger_up(c, t):
    return not any(c == oc and s <= t < e for oc, s, e, _ in OUTAGES)


def side_for(robot, t):
    g = GROUP[robot]
    if g == "G3" and REROUTE_G3[0] <= t < REROUTE_G3[1]:
        return "west"
    return "east" if g in ("G3", "G4") else "west"


def override(robot, t):
    for s, e, st, z, code in OVERRIDES.get(robot, []):
        if s <= t < e:
            return st, z, code
    return None


# Battery wear differs per robot, so discharge rates differ slightly
_wear = random.Random(3)
WEAR = {r: round(_wear.uniform(0.9, 1.1), 3) for r in ROBOTS}
WEAR["R31"] = 0.93
WEAR.update({"R18": 0.86, "R15": 0.95, "R16": 1.08, "R19": 1.13, "R21": 0.9})


def drain(t, r=None):
    h = (t // 60) % 24
    return (0.08 if (h >= 22 or h < 6) else 0.11) * (WEAR[r] if r else 1)


def simulate(init):
    """Minute simulation. Returns per-minute state table and an event list."""
    st = {r: {"state": "WORK", "bat": init[r], "travel": 0, "side": None, "chg": None, "q_at": None,
              "lost": False} for r in ROBOTS}
    table = {r: [None] * MINUTES for r in ROBOTS}
    events = []
    busy = {c: None for c in WEST + EAST}
    for t in range(MINUTES):
        # chargers that just failed kick off their robot
        for c, r in list(busy.items()):
            if r and not charger_up(c, t):
                busy[c] = None
                s = st[r]
                s.update(state="QUEUED", chg=None, q_at=t)
                events.append((t, "kicked", r, c))
        for r in ROBOTS:
            s = st[r]
            ov = override(r, t)
            if ov and s["state"] == "WORK":
                s["bat"] -= 0.03
                table[r][t] = (ov[0], round(s["bat"], 1), ov[1], ov[2], "")
                continue
            if s["state"] == "WORK":
                s["bat"] -= drain(t, r)
                if r == "R31" and s["state"] == "WORK" and s["lost"]:
                    if s["bat"] <= CRIT:
                        s["state"] = "CRIT"
                        events.append((t, "critical", r, None))
                elif s["bat"] <= SEEK:
                    if r == "R31" and R31_LOST[0] <= t < R31_LOST[1]:
                        s["lost"] = True
                        events.append((t, "seek_lost", r, None))
                    else:
                        s.update(state="TO_CHG", travel=3, side=side_for(r, t))
                        events.append((t, "seek", r, s["side"]))
            elif s["state"] == "CRIT":
                if t >= R31_TOW:
                    s.update(state="TO_CHG", travel=1, side="west", lost=False)
                    events.append((t, "towed", r, "west"))
            elif s["state"] == "TO_CHG":
                s["bat"] -= 0.11
                s["travel"] -= 1
                if s["travel"] <= 0:
                    s.update(state="QUEUED", q_at=t)
                    events.append((t, "arrive", r, s["side"]))
            elif s["state"] == "QUEUED":
                s["bat"] -= 0.05
                if side_for(r, t) != s["side"]:
                    s.update(state="TO_CHG", travel=4, side=side_for(r, t))
                    events.append((t, "reroute", r, s["side"]))
            elif s["state"] == "CHARGING":
                s["bat"] = min(FULL, s["bat"] + CHG_RATE)
                if s["bat"] >= FULL:
                    busy[s["chg"]] = None
                    events.append((t, "charge_end", r, s["chg"]))
                    s.update(state="RETURN", travel=2, chg=None)
            elif s["state"] == "RETURN":
                s["travel"] -= 1
                if s["travel"] <= 0:
                    s["state"] = "WORK"
        # allocate free chargers to queued robots, first come first served
        queued = sorted((st[r]["q_at"], r) for r in ROBOTS if st[r]["state"] == "QUEUED")
        for _, r in queued:
            s = st[r]
            pool = WEST if s["side"] == "west" else EAST
            if GROUP[r] == "G3" and G3_ANY[0] <= t < G3_ANY[1]:
                pool = ["C1", "C3", "C2"]
            for c in pool:
                if busy[c] is None and charger_up(c, t):
                    busy[c] = r
                    s.update(state="CHARGING", chg=c)
                    events.append((t, "charge_start", r, c))
                    break
        for r in ROBOTS:
            s = st[r]
            if table[r][t] is None:
                zone = {"CHARGING": CHG_ZONE.get(s["side"], ""), "QUEUED": CHG_ZONE.get(s["side"], ""),
                        "CRIT": "TR-2"}.get(s["state"], "")
                code = {"CRIT": "AMR-112", "TO_CHG": "AMR-101"}.get(s["state"], "")
                table[r][t] = (s["state"], round(s["bat"], 1), zone, code, s["chg"] or "")
    return table, events


def tune():
    rng = random.Random(7)
    init = {r: round(rng.uniform(25, 88), 1) for r in ROBOTS}
    for _ in range(300):
        table, events = simulate(init)
        seeks = {}
        for t, kind, r, _ in events:
            if kind in ("seek", "seek_lost"):
                seeks.setdefault(r, []).append(t)
        changed = False
        for r, target in TARGETS.items():
            near = min(seeks.get(r, [10 ** 6]), key=lambda x: abs(x - target))
            tol = 6 if r == "R31" else 1
            if abs(near - target) > tol:
                init[r] += (target - near) * 0.04 if abs(near - target) < 400 else 20
                changed = True
        for r, (a, b) in AVOID.items():
            if any(a <= t <= b for t in seeks.get(r, [])):
                init[r] += 9
                changed = True
        for r in init:
            while init[r] > 89:
                init[r] -= 70
            while init[r] < 16:
                init[r] += 70
        if not changed:
            return init, table, events
    raise SystemExit("tuning did not converge")


init, TABLE, EVENTS = tune()
rng = random.Random(42)

# ---------------------------------------------------------------- telemetry
AISLES = [f"A0{i}" for i in range(1, 9)]
TRANSIT = ["TR-1", "TR-2", "TR-3"]
STATE_OUT = {"WORK": None, "TO_CHG": "TO_CHARGE", "QUEUED": "QUEUED_CHARGE", "CHARGING": "CHARGING",
             "RETURN": "MOVING", "CRIT": "FAULT", "FAULT": "FAULT", "BLOCKED": "BLOCKED"}


def telemetry_row(r, t):
    state, bat, zone, code, chg = TABLE[r][t]
    g = GROUP[r]
    out_state = STATE_OUT[state]
    if out_state is None:
        night = (t // 60) % 24 in (22, 23, 0, 1, 2, 3, 4, 5)
        pick = rng.random()
        if pick < (0.25 if night else 0.12):
            out_state, zone = "IDLE", f"PARK-{g}"
        elif pick < 0.55:
            out_state, zone = "MOVING", rng.choice(AISLES + TRANSIT)
        elif pick < 0.8:
            out_state, zone = "DELIVERING", f"{STATION[g]}-IN"
        else:
            out_state, zone = "AT_STATION", STATION[g]
    if out_state in ("TO_CHARGE", "MOVING") and not zone:
        zone = rng.choice(TRANSIT)
    return [ts(t), r, g, STATION[g], f"{max(bat, 0):.1f}", out_state, zone, code, chg]


minute_windows = {
    **{r: (hm(2, 13, 50), hm(2, 14, 55)) for r in ROBOTS if GROUP[r] == "G3"},
    **{r: (hm(1, 9, 35), hm(1, 10, 10)) for r in ["R03", "R05", "R07"]},
    "R31": (hm(2, 5, 35), hm(2, 7, 0)),
}
rows = []
for t in range(MINUTES):
    for r in ROBOTS:
        w = minute_windows.get(r)
        if t % 60 == 0 or (w and w[0] <= t <= w[1]):
            rows.append(telemetry_row(r, t))
with open(OUT / "robot_telemetry.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "robot_id", "group", "assigned_station", "battery_pct", "state", "zone",
                "fault_code", "charger_id"])
    w.writerows(rows)

# ---------------------------------------------------------------- WCS / fleet / equipment log
LOG = []


def log(t, sec, level, source, entity, code, msg):
    LOG.append((t * 60 + sec, f"{ts(t, sec)} | {level:<5} | {source:<8} | {entity:<6} | {code or '-':<8} | {msg}"))




def new_task(t):
    """Task and tote IDs grow with time (about 33 tasks a minute site-wide)."""
    return f"T-{480211 + t * 33 + rng.randint(0, 32)}", f"TT-{70412 + t * 3 + rng.randint(0, 2)}"


def working_robot(g, t):
    pool = [r for r in ROBOTS if GROUP[r] == g and TABLE[r][t][0] == "WORK"]
    return rng.choice(pool) if pool else None


PS3_DARK = (hm(2, 14, 10), hm(2, 14, 46))  # no G3 robot can take PS3 tasks
PS4_6_REJECT = (hm(1, 16, 18), hm(1, 16, 53))
PS5_JAM = (hm(2, 11, 12), hm(2, 11, 44))

# background traffic: a sample of task lifecycles roughly every 6 minutes
for t in range(0, MINUTES, 12):
    t2 = t + rng.randint(0, 11)
    st = rng.choice(list(STATION.values()))
    g = "G" + st[2]
    if g == "G3" and PS3_DARK[0] <= t2 < PS3_DARK[1]:
        continue
    if st in ("PS4", "PS6") and PS4_6_REJECT[0] <= t2 < PS4_6_REJECT[1]:
        continue
    task, tote = new_task(t2)
    loc = f"L-{rng.randint(1, 12):02d}-{rng.randint(1, 40):02d}-{rng.randint(1, 6)}"
    log(t2, rng.randint(0, 59), "INFO", "WMS", st, "", f"TASK_CREATE {task} tote {tote} from {loc} to {st}")
    r = working_robot(g, t2)
    if r is None:
        continue
    if t2 + 1 < MINUTES:
        log(t2 + 1, rng.randint(0, 59), "INFO", "WCS", r, "", f"TASK_ASSIGN {task} -> {r} (group {g})")
    if t2 + 5 < MINUTES:
        log(t2 + 5, rng.randint(0, 59), "INFO", "FLEET", r, "",
            f"TASK_COMPLETE {task} tote {tote} delivered to {st} in {rng.randint(3, 6)}m{rng.randint(0, 59):02d}s")

# waves and fleet status
for t in range(0, MINUTES, 30):
    if t % 60 == 0:
        log(t, 5, "INFO", "WMS", "-", "", f"WAVE_RELEASE W-{5600 + t // 60} released {rng.randint(1700, 2200)} order lines")
    counts = {}
    for r in ROBOTS:
        counts[TABLE[r][t][0]] = counts.get(TABLE[r][t][0], 0) + 1
    active = counts.get("WORK", 0) + counts.get("RETURN", 0) + counts.get("TO_CHG", 0)
    log(t, 30, "INFO", "FLEET", "-", "",
        f"FLEET_STATUS active={active} charging={counts.get('CHARGING', 0)} queued_charge={counts.get('QUEUED', 0)} "
        f"blocked={counts.get('BLOCKED', 0)} fault={counts.get('FAULT', 0) + counts.get('CRIT', 0)}")

# charging events from the simulation
for t, kind, r, x in EVENTS:
    g = GROUP[r]
    sec = {"charge_end": rng.randint(0, 25), "charge_start": rng.randint(30, 59),
           "reroute": rng.randint(10, 59), "kicked": rng.randint(15, 59)}.get(kind, rng.randint(0, 59))
    if kind == "seek":
        aff = "C1,C3" if x == "west" else "C2,C4"
        log(t, sec, "INFO", "FLEET", r, "AMR-101", f"Charge request at {TABLE[r][t][1]:.0f}% (group {g}, affinity {aff})")
    elif kind == "arrive":
        side_chargers = WEST if x == "west" else EAST
        down = [c for c in side_chargers if not charger_up(c, t)]
        busy_now = [c for c in side_chargers if c not in down]
        if down:
            reason = ", ".join(f"{c} {'MAINTENANCE' if c == 'C4' and t < hm(2, 17, 30) else 'FAULT'}" for c in down)
            log(t, sec, "WARN", "FLEET", r, "", f"Arrived {CHG_ZONE[x]}; queued for charge (unavailable: {reason})")
    elif kind == "charge_start":
        log(t, sec, "INFO", "CHARGER", x, "", f"CHARGE_START {r} SoC {TABLE[r][t][1]:.0f}%")
    elif kind == "charge_end":
        log(t, sec, "INFO", "CHARGER", x, "", f"CHARGE_END {r} SoC 90%")
    elif kind == "kicked":
        log(t, sec, "WARN", "CHARGER", x, "", f"Charging of {r} interrupted")
    elif kind == "reroute":
        log(t, sec, "INFO", "FLEET", r, "", f"Leaving queue: charger affinity now {x}")

# ---- A: blocked aisle
log(hm(1, 9, 41), 7, "ERROR", "FLEET", "R07", "AMR-305", "Safety field obstruction - emergency stop in aisle A04")
log(hm(1, 9, 43), 22, "WARN", "FLEET", "R03", "AMR-207", "Path blocked >120 s in aisle A04 (obstacle: R07)")
log(hm(1, 9, 46), 51, "WARN", "FLEET", "R05", "AMR-207", "Path blocked >120 s in aisle A04 (obstacle: R03)")
log(hm(1, 10, 1), 40, "INFO", "FLEET", "A04", "", "Aisle A04 maintenance mode ON (user eng_oncall)")
log(hm(1, 10, 5), 2, "INFO", "FLEET", "R07", "", "E-stop reset; robot available")
log(hm(1, 10, 5), 30, "INFO", "FLEET", "A04", "", "Aisle A04 maintenance mode OFF (user eng_oncall)")

# ---- B: slotting update -> WCS-402 rejects
log(hm(1, 16, 15), 12, "INFO", "WMS", "-", "", "Slotting batch SLT-8841 applied: 212 locations re-coded (range L-07-*)")
for i, m in enumerate(range(hm(1, 16, 18), hm(1, 16, 50))):
    for _ in range(rng.randint(1, 2)):
        task, tote = new_task(m)
        st = "PS4" if rng.random() < 0.55 else "PS6"
        log(m, rng.randint(0, 59), "ERROR", "WCS", st, "WCS-402",
            f"TASK_REJECT {task}: unknown storage location L-07-{rng.randint(1, 40):02d}-{rng.randint(1, 6)}")
log(hm(1, 16, 49), 10, "INFO", "WCS", "-", "", "Location master resync started (user eng_oncall)")
log(hm(1, 16, 52), 44, "INFO", "WCS", "-", "", "Location master resync complete: 212 locations added")
log(hm(1, 16, 53), 30, "INFO", "WMS", "-", "", "Resent 61 rejected tasks")

# ---- C: fleet manager restart, R31 runs flat
log(hm(2, 5, 41), 0, "WARN", "FLEET", "-", "", "Fleet manager service restart (scheduled patch FM-3.8.2)")
log(hm(2, 5, 42), 18, "ERROR", "FLEET", "-", "AMR-410", "Heartbeat timeout: 40 robots (fleet manager unavailable)")
log(hm(2, 5, 43), 51, "INFO", "FLEET", "-", "", "Fleet manager online; 40 robots reconnected")
crit_t = next(t for t, k, r, _ in EVENTS if k == "critical")
log(crit_t, 9, "ERROR", "FLEET", "R31", "AMR-112", "Battery critical (10%) - robot stopped in TR-2")
log(hm(2, 6, 41), 25, "INFO", "FLEET", "R31", "", "Manual mode (user eng_early)")

# ---- D: conveyor merge M2
for m, s in [(hm(2, 11, 12), 4), (hm(2, 11, 24), 37), (hm(2, 11, 31), 15)]:
    log(m, s, "ERROR", "CONVEYOR", "M2", "CNV-501", "Merge M2 photo-eye PE-M2-03 blocked >30 s")
    log(m + 1, s, "WARN", "CONVEYOR", "PS5", "CNV-520", "Outbound spur PS5 full - station paused")
log(hm(2, 11, 19), 3, "INFO", "CONVEYOR", "M2", "", "Merge M2 cleared (operator reset)")
log(hm(2, 11, 27), 40, "INFO", "CONVEYOR", "M2", "", "Merge M2 cleared (operator reset)")
log(hm(2, 11, 38), 0, "INFO", "CONVEYOR", "M2", "", "Section M2 stopped and locked out (user eng_oncall)")
log(hm(2, 11, 44), 20, "INFO", "CONVEYOR", "M2", "", "Section M2 restarted; 3 totes passed merge")

# ---- E: the demo incident
log(hm(2, 12, 30), 0, "INFO", "CHARGER", "C4", "CHG-250", "Planned maintenance: firmware upgrade, out of service until 17:30")
log(hm(2, 14, 2), 14, "ERROR", "CHARGER", "C2", "CHG-214", "Output contactor fault - charging halted")
log(hm(2, 14, 5), 33, "ERROR", "WCS", "PS5", "WCS-402", f"TASK_REJECT {new_task(hm(2, 14, 5))[0]}: unknown storage location L-02-14-3")  # red herring
log(hm(2, 14, 12), 48, "WARN", "FLEET", "R17", "AMR-207", "Path blocked >120 s in CHG-CORR-E (obstacle: R21 queued)")
log(hm(2, 14, 13), 55, "WARN", "FLEET", "R20", "AMR-207", "Path blocked >120 s in CHG-CORR-E (obstacle: R17)")
log(hm(2, 14, 9), 41, "INFO", "FLEET", "R20", "", f"TASK_COMPLETE {new_task(hm(2, 14, 5))[0]} tote {new_task(hm(2, 14, 5))[1]} delivered to PS3 in 4m02s")
pending = 0
for m in range(hm(2, 14, 11), hm(2, 14, 47), 2):
    pending += rng.randint(2, 4)
    task, tote = new_task(m)
    log(m, rng.randint(0, 59), "WARN", "WCS", "PS3", "WCS-430",
        f"Task {task} for PS3 pending: no available robot in group G3 (pending for PS3: {pending})")
log(hm(2, 14, 34), 5, "INFO", "CONFIG", "G3", "", "Charger affinity changed: G3 C2,C4 -> C1,C3 (user eng_oncall)")
log(hm(2, 14, 38), 12, "INFO", "FLEET", "R17", "", "Path clear; resuming")
log(hm(2, 14, 38), 40, "INFO", "FLEET", "R20", "", "Path clear; resuming")
log(hm(2, 14, 40), 2, "INFO", "CHARGER", "C2", "", "Isolated and power-cycled (user eng_oncall)")
log(hm(2, 14, 41), 30, "INFO", "CHARGER", "C2", "", "Self-test passed; charger available")
log(hm(2, 14, 48), 16, "INFO", "FLEET", "R17", "", f"TASK_COMPLETE {new_task(hm(2, 14, 38))[0]} tote {new_task(hm(2, 14, 38))[1]} delivered to PS3 in 9m58s")
log(hm(2, 14, 45), 0, "INFO", "CONFIG", "G3", "", "Charger affinity changed: G3 C1,C3 -> C1,C2,C3 (user eng_oncall)")
log(hm(2, 16, 0), 0, "INFO", "CONFIG", "G3", "", "Charger affinity changed: G3 C1,C2,C3 -> C2,C4 (user eng_oncall)")
log(hm(2, 17, 30), 0, "INFO", "CHARGER", "C4", "", "Maintenance complete; charger available")

LOG.sort()
with open(OUT / "wcs_messages.log", "w") as f:
    f.write("# timestamp | level | source | entity | code | message\n")
    f.write("# Filtered extract from the WCS, fleet manager, charger and conveyor controllers. Local time.\n")
    for _, line in LOG:
        f.write(line + "\n")

# ---------------------------------------------------------------- pick station events (15-min intervals)
BREAKS = {s: [(h * 60 + 15 * (int(s[2]) - 1)) for h in (2, 10, 19)] for s in STATION.values()}
rows = []
for t0 in range(0, MINUTES, 15):
    hour = (t0 // 60) % 24
    base = 300 if (hour >= 22 or hour < 6) else 350
    for g, st in STATION.items():
        robots = [r for r in ROBOTS if GROUP[r] == g]
        avail = sum(TABLE[r][t][0] in ("WORK", "RETURN") for r in robots for t in range(t0, t0 + 15)) / (15 * len(robots))
        factor = min(1.0, avail / 0.7) * rng.uniform(0.93, 1.05)
        idle, note, logged = 0, "", "Y"
        last_tote = (BASE + timedelta(minutes=t0 + 14, seconds=rng.randint(0, 59))).strftime("%H:%M:%S")
        if (t0 % 1440) in BREAKS[st]:
            factor, idle, note, logged, last_tote = 0, 15, "Operator break", "N", ""
        if st == "PS1" and hm(1, 9, 45) <= t0 < hm(1, 10, 15):
            factor, idle = factor * 0.45, 6
        if st in ("PS4", "PS6") and PS4_6_REJECT[0] - 3 <= t0 < PS4_6_REJECT[1]:
            factor, idle = factor * 0.55, 5
        if st == "PS5" and hm(2, 6, 15) <= t0 < hm(2, 7, 0):
            factor *= 0.85
        if st == "PS5" and hm(2, 11, 0) <= t0 < hm(2, 11, 45):
            factor, idle, note = factor * 0.4, 8, "Outbound spur full"
        if st == "PS3" and t0 == hm(2, 14, 0):
            factor, idle, last_tote = 0.62, 5, "14:09:41"
        elif st == "PS3" and t0 in (hm(2, 14, 15), hm(2, 14, 30)):
            factor, idle, last_tote = 0, 15, ""
        elif st == "PS3" and t0 == hm(2, 14, 45):
            factor, idle, last_tote = 0.4, 6, "14:59:20"
        elif st == "PS3" and t0 == hm(2, 15, 0):
            factor *= 0.8
        picks = round(base / 4 * factor)
        totes = round(picks / rng.uniform(2.8, 3.2)) if picks else 0
        rows.append([ts(t0), st, logged, totes, picks, picks * 4, idle, last_tote if totes else "", note])
with open(OUT / "pick_station_events.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["interval_start", "station_id", "operator_logged_in", "totes_arrived", "picks_completed",
                "picks_per_hour", "idle_minutes", "last_tote_arrival", "note"])
    w.writerows(rows)

print("start batteries tuned; telemetry rows:", sum(1 for _ in open(OUT / "robot_telemetry.csv")) - 1,
      "| log lines:", len(LOG), "| station rows:", len(rows))

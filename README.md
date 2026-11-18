# PickPath Copilot: fictional dataset

Data for an AI incident copilot prototype at **Northgate Fulfilment**, a fictional 24/7 e-commerce distribution centre. Every site, system, robot, code and ticket here is invented.

## The site

| Item | Detail |
|---|---|
| Robots | 40 AMRs, R01-R40, in six groups. Group Gn serves pick station PSn (G1 = R01-R07, G2 = R08-R14, G3 = R15-R21, G4 = R22-R27, G5 = R28-R34, G6 = R35-R40) |
| Chargers | C1, C3 in CHG-WEST; C2, C4 in CHG-EAST |
| Charger affinity | G1, G2, G5, G6 use west; G3, G4 use east. No automatic failover |
| Battery rules | Seek charge at 15%, critical stop at 10%, charge to 90% |
| Pick stations | PS1-PS6, target 350 picks an hour (300 at night) |
| Time span | Tue 10 Nov 2026 00:00 to Wed 11 Nov 2026 23:59, local time |

## Files

| File | Contents | Size |
|---|---|---|
| `data/robot_telemetry.csv` | Hourly snapshot of every robot, plus minute-level rows around incidents | 2,564 rows |
| `data/fault_codes.csv` | Fault code reference with linked runbook | 30 codes |
| `data/wcs_messages.log` | Filtered extract from the WMS, WCS, fleet manager, chargers and conveyors | 1,416 lines |
| `data/pick_station_events.csv` | 15-minute station summaries: totes, picks, idle minutes, last tote arrival | 1,152 rows |
| `data/incident_tickets.json` | Past incidents Aug-Nov 2026 with notes, root cause and fix | 20 tickets |
| `data/runbooks/` | RB-01 charger failure, RB-02 blocked aisle, RB-03 message rejects, RB-04 low battery, RB-05 conveyor jam | 5 files |
| `eval/test_incidents.json` | Five planted incidents with the expected answer, for the accuracy check | 5 cases |
| `scripts/generate_data.py` | Regenerates telemetry, log and station files (deterministic) | |

## The demo incident

> "Pick station 3 has been idle for 12 minutes. Operators are waiting for totes." (reported Wed 11 Nov, 14:21)

| Time | Evidence | Where |
|---|---|---|
| 12:30 | C4 goes into planned maintenance (CHG-250) until 17:30 | log |
| 14:00-14:08 | R18, R15, R16, R19, R21 request charge at 15% (affinity C2, C4) | log, telemetry |
| 14:02:14 | **C2 raises CHG-214, output contactor fault** | log |
| 14:03-14:10 | All five arrive at CHG-EAST and queue: "unavailable: C2 FAULT, C4 MAINTENANCE" | log, telemetry |
| 14:09:41 | Last tote delivered to PS3 | log, station events |
| 14:10-14:11 | R17 and R20 blocked in the east charging corridor behind the queue (AMR-207) | log, telemetry |
| 14:11 on | WCS-430: PS3 tasks pending, no available robot in G3 | log |
| 14:21 | All 7 G3 robots unavailable; queued robots at 13-14% | telemetry |

**Expected answer:** charger C2 failure, with C4 already in maintenance, has left every G3 robot queued or blocked. Runbook RB-01: change G3 affinity to C1 and C3, then power-cycle C2. Matches INC-0142. Engineer approval required.

**Traps that test the copilot's reasoning:** INC-0137 has the same symptom but a scanner cause (totes were arriving then; here they are not), and a WCS-402 reject for PS5 at 14:05 is unrelated.

**Use `as_of` when retrieving evidence.** The files also record what happened after the report (the engineer's fix at 14:34-14:45 and recovery at 14:48). For a fair demo, filter log and telemetry to times at or before the incident's report time so the copilot cannot read the answer.

## Other planted incidents

| When | Incident | Best fix type |
|---|---|---|
| Tue 09:41 | R07 safety stop in aisle A04, R03 and R05 blocked; PS1 slows | AI copilot |
| Tue 16:15 | WMS slotting update causes WCS-402 rejects; PS4 and PS6 short of work | Automated check and alert |
| Wed 05:41 | Fleet manager restart loses R31's charge request; R31 stops at 10% in TR-2 at 06:39 | Better alerting |
| Wed 11:12 | Repeated jam at conveyor merge M2; PS5 outbound spur full | Runbook and maintenance fix |

These map to the judgement table in the case study. Operator breaks (operator_logged_in = N) appear three times a day per station; they are normal idle time, not incidents.

## Regenerate

```
python3 scripts/generate_data.py
```
Output is identical on every run.

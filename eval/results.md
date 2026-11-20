# PickPath accuracy check (20 Nov 2026 21:14)

**Correct root cause: 5 of 5 known incidents**  
**Honest on unknown incidents: 2 of 2** (nothing invented, no false match, says when the evidence is not enough)

| Test | Incident | Pass | Similar ticket | Runbook | Invalid citations | Status | Confidence | Likely cause |
|---|---|---|---|---|---|---|---|---|
| TEST-01 | Demo: charger failure | ✅ | ✅ | ✅ | INC-0130 | recommendation | high | Both east-side chargers (C2 faulted, C4 on planned maintenance) are unavailable, leaving all 7 G3 robots unable to charge; 5 are queued at CHG-EAST and 2 are blocked in the corridor behind them, starving PS3 of totes. |
| TEST-02 | Blocked aisle | ✅ | ✅ | ✅ | none | recommendation | high | R07 triggered an emergency stop in aisle A04 due to a safety field obstruction (AMR-305), blocking R03 and R05 behind it and slowing PS1 tote delivery. |
| TEST-03 | Message rejects | ✅ | ✅ | ✅ | none | recommendation | high | WMS slotting batch SLT-8841 re-coded 212 locations in the L-07 range at 16:15 before the WCS location master was synchronised, causing WCS to reject all tasks referencing those locations and starving PS4 and PS6 of work. |
| TEST-04 | Low battery | ✅ | ✅ | ✅ | none | recommendation | high | R31 ran its battery down to critical (10%) because its charge request was lost during the scheduled fleet manager restart at 05:41, mirroring INC-0130. |
| TEST-05 | Conveyor jam | ✅ | ✅ | ✅ | none | recommendation | high | Recurring tote jam at merge M2 caused by misaligned or loose photo-eye PE-M2-03 bracket blocking the outbound conveyor from PS5. |
| TEST-06 | Unknown: new software bug | ✅ | ✅ | ✅ | none | recommendation | medium | WCS task allocator (release 5.8.2, reloaded at 19:30) is repeatedly assigning tasks to already-busy G6 robots, causing 90-second re-queue delays that starve PS6 of totes. |
| TEST-07 | Unknown: nothing to go on | ✅ | ✅ | ✅ | none | insufficient_evidence | low | A software or data mismatch is serving incorrect product images to the PS2 display — possibly a stale cache, a failed content sync, or a WCS/UI configuration error on the PS2 terminal. |

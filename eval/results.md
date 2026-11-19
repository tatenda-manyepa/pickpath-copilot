# PickPath accuracy check (19 Nov 2026 20:16)

**Correct root cause: 5 of 5**

| Test | Incident | Cause | Similar ticket | Runbook | Invalid citations | Confidence | Likely cause |
|---|---|---|---|---|---|---|---|
| TEST-01 | Demo: charger failure | ✅ | ✅ | ✅ | none | high | Both east-side chargers (C2 faulted, C4 on planned maintenance) are unavailable, leaving all 7 G3 robots unable to charge; 5 are queued at CHG-EAST and 2 are blocked in the corridor behind them, starving PS3 of totes. |
| TEST-02 | Blocked aisle | ✅ | ✅ | ✅ | none | high | R07 triggered an emergency stop in aisle A04 due to a safety field obstruction (debris or fallen tote), blocking R03 and R05 behind it and slowing PS1 tote delivery. |
| TEST-03 | Message rejects | ✅ | ✅ | ✅ | none | high | WMS slotting batch SLT-8841 re-coded 212 locations in the L-07 range at 16:15 before the WCS location master was synchronised, causing WCS to reject all tasks referencing those locations. |
| TEST-04 | Low battery | ✅ | ✅ | ✅ | none | high | R31 ran its battery down to critical (10%) because its charge request was lost during the scheduled fleet manager restart at 05:41, mirroring INC-0130. |
| TEST-05 | Conveyor jam | ✅ | ✅ | ✅ | none | high | Recurring tote jam at merge M2 caused by misaligned or loose photo-eye PE-M2-03 bracket blocking the outbound conveyor from PS5. |

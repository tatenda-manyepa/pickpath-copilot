# RB-01 Charger failure or charger unavailable

**Applies to:** CHG-201, CHG-214, CHG-220, CHG-230, CHG-250
**Typical symptom:** robots queuing in a charging zone; a pick station starved of totes even though its operator is ready.

## Site background
- Four chargers: **C1, C3** in CHG-WEST; **C2, C4** in CHG-EAST.
- Charger affinity: groups **G1, G2, G5, G6 → C1, C3** (west); groups **G3, G4 → C2, C4** (east).
- Robots seek charge at 15% and stop at 10% (AMR-112).
- If both chargers on one side are unavailable, robots on that side queue and do **not** fail over automatically.

## Steps
1. In the fleet manager, check charger status. Note which chargers are FAULT, OFFLINE or MAINTENANCE.
2. Count robots in QUEUED_CHARGE and BLOCKED in the charging zone and its corridor. Note their groups and battery levels.
3. If robots are queuing for an unavailable charger, **change the affected groups' charger affinity to the other side** (for east groups: C1, C3). Robots below 12% go first.
4. Try to recover the charger:
   - CHG-201 (offline): power-cycle the charger controller; check the network switch.
   - CHG-214 (contactor fault): power-cycle the charger at its isolator. If the fault returns within an hour, leave it isolated and raise a maintenance request for contactor replacement.
   - CHG-220 (over-temperature): clear the vents; wait 10 minutes.
   - CHG-230 (docking): check contacts and floor alignment marks.
5. When the charger has been stable for 30 minutes, restore the normal affinity.
6. Record queue length, affected stations and time to recovery in the ticket.

## Safety
Isolate the charger before opening the cabinet. Do not push robots by hand in the charging zone while other robots are docking.

# RB-04 Robot low or critical battery

**Applies to:** AMR-101, AMR-112, AMR-120
**Typical symptom:** a robot stopped in a lane at 10% or lower.

## Steps
1. Confirm the robot is in AMR-112 (critical stop) and note its location.
2. Check whether a charge request (AMR-101) was raised and whether it was queued. If not, check for fleet manager restarts or heartbeat timeouts around that time.
3. Put the robot into manual mode and push it to the nearest free charger using the tow handle.
4. If several robots are low at once, follow RB-01 instead: the cause is usually charger capacity.
5. Check the robot's battery health report if it ran down faster than its peers.

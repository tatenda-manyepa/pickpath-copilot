# RB-02 Robot fault blocking an aisle

**Applies to:** AMR-305, AMR-310, AMR-207
**Typical symptom:** one robot stopped in an aisle or transit lane; robots behind it report path blocked (AMR-207); the stations they serve slow down.

## Steps
1. Find the first robot in the chain: the one in FAULT (usually AMR-305 or AMR-310). Robots reporting only AMR-207 are waiting behind it.
2. Put the aisle into **maintenance mode** in the fleet manager so no new robots are routed into it.
3. Go to the robot with a hi-vis vest and the aisle lock-out tag. Check for debris (shrink-wrap, strapping, labels), a fallen tote or a person in the safety field.
4. Remove the cause, then clear the e-stop on the robot's panel.
5. Release the aisle from maintenance mode. Blocked robots resume on their own.
6. If the same robot faults again within 24 hours, take it out of service for inspection.

## Safety
Never enter an aisle without setting maintenance mode first.

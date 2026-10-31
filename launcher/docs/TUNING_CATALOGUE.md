# Tuning catalogue - the values a data mod can change

Use the exact key in a mod.toml:

```toml
[bmashup.tune]
version = 1
set = ["Score/Burnout Points | Takedown BP = 2500"]
```

Limits: 0 .. 16 x the game's value (at least 0 .. 16); a value outside is refused with the reason in the log. The game's value below is what the game ships with; the host checks every value on your game build at start and names any it could not verify.

Rows from host additions (`bm_tune_catalog_*.inc`, e.g. Air Ram, AI) need the host version named in the release notes; the launcher's compatibility check tells you when a host does not know a key.

| Key (Group \| Name) | Type | Game value |
|---|---|---|
| `Boost Bar \| Minimum Boost Time (seconds)` | decimal | 1 |
| `Boost Bar \| Minimum Boost Recovery Time (seconds)` | decimal | 0.5 |
| `Boost Bar \| Boost Bar sizes (Boost Units)` | decimal | 240 |
| `Boost Bar \| Boost Earning Multiplier` | decimal | 1 |
| `Boost Bar \| Boost Rate (Boost Units per Second)` | decimal | 36 |
| `Score/Boost/Air \| Minimum Air Distance (Metres)` | decimal | 5 |
| `Score/Boost/Air \| Boost value per Air metre (Boost units)` | decimal | 2 |
| `Score/Boost/Oncoming \| Minimum Oncoming Speed (MPH)` | decimal | 30 |
| `Score/Boost/Oncoming \| Minimum Oncoming Distance (Metres)` | decimal | 10 |
| `Score/Boost/Oncoming \| Boost value per Oncoming metre (Boost units)` | decimal | 0.3 |
| `Score/Boost/Drift \| Minimum Drift Speed (MPH)` | decimal | 30 |
| `Score/Boost/Drift \| Minimum Drift Distance (Metres)` | decimal | 10 |
| `Score/Boost/Drift \| Boost value per Drift metre (Boost units)` | decimal | 1 |
| `Score/Boost/Near Miss \| Near Miss Distance (Metres)` | decimal | 2 |
| `Score/Boost/Near Miss \| Minimum Near Miss Speed (MPH)` | decimal | 30 |
| `Score/Boost/Near Miss \| Minimum Near Miss Chain Speed (MPH)` | decimal | 30 |
| `Score/Boost/Near Miss \| Boost value per Near Miss (Boost units)` | decimal | 60 |
| `Score/Boost/Near Miss \| Near Miss Chain Time (Seconds)` | decimal | 5 |
| `Score/Boost/Crash Escape \| Crash Escape Radius` | decimal | 8 |
| `Score/Boost/Crash Escape \| Time Between Crashing Near Misses (Seconds)` | decimal | 1 |
| `Score/Boost/Crash Escape \| Minimum Time Clear After Crash Escape` | decimal | 3 |
| `Score/Boost/Crash Escape \| Minimum Crash Escape Speed (MPH)` | decimal | 70 |
| `Score/Boost/Crash Escape \| Boost value per Crash Escape (Boost units)` | decimal | 120 |
| `Score/Boost/Aggressive \| Boost value lost or gained per Slam (Boost units)` | decimal | 360 |
| `Score/Boost/Aggressive \| Min Contact Time For Rubbing (Seconds)` | decimal | 0.3 |
| `Score/Boost/Aggressive \| Boost value for rubbing (Boost units)` | decimal | 15 |
| `Score/Boost/Boost Start \| Boost Start Boost value (Boost units)` | decimal | 50 |
| `Score/Boost/Takedowns \| Takedown Boost value (Boost units)` | decimal | 720 |
| `Score/Boost/Takedowns \| Race Car Clear Wait Time (Seconds)` | decimal | 1 |
| `Score/Boost/Takedowns \| Maximum Crash Wait Time (Seconds)` | decimal | 1 |
| `Score/Boost/Takedowns \| Maximum Crash Wait Time - No Slam (Seconds)` | decimal | 0.5 |
| `Score/Boost/Takedowns \| Minimum Collide Time to enable Takedown - No Slam (Seconds)` | decimal | 0.5 |
| `Score/Boost/Takedowns \| Time window for getting a double takedown(Seconds)` | decimal | 1 |
| `Score/Boost/Takedowns \| Time window for getting a takedown spree (Seconds)` | decimal | 30 |
| `Score/Boost/Takedowns \| Time window for getting a double revenge takedown (Seconds)` | decimal | 60 |
| `Score/Boost/Props \| Prop Hit Chain time (Seconds)` | decimal | 2 |
| `Score/Boost/Props \| Prop Hit Boost value (Boost units)` | decimal | 3 |
| `Score/Boost/Lap \| Perfect Lap Boost value (Boost units)` | decimal | 120 |
| `Score/Boost/Lap \| Burnout Lap Boost value (Boost units)` | decimal | 240 |
| `Score/Boost/Aggressive \| Trading Paint Boost value (Boost units)` | decimal | 3 |
| `Score/Burnout Points \| Prop Hit BP` | whole number | 10 |
| `Score/Burnout Points \| Rubbing BP` | whole number | 5 |
| `Score/Burnout Points \| Tradin' Paint BP` | whole number | 25 |
| `Score/Burnout Points \| Boost Start BP` | whole number | 50 |
| `Score/Burnout Points \| Crash Escape BP` | whole number | 100 |
| `Score/Burnout Points \| Burning Slam Extra BP` | whole number | 15 |
| `Score/Burnout Points \| Slam Type BP` | whole number | 20 |
| `Score/Burnout Points \| Super Slam Type BP` | whole number | 30 |
| `Score/Burnout Points \| Perfect Lap BP` | whole number | 500 |
| `Score/Burnout Points \| Takedown BP` | whole number | 1000 |
| `Score/Burnout Points \| Revenge Takedown Bonus BP` | whole number | 350 |
| `Score/Burnout Points \| Psyche Out BP` | whole number | 150 |
| `Score/Burnout Points \| Aftertouch Takedown BP` | whole number | 250 |
| `Score/Burnout Points \| Burnout Lap BP` | whole number | 1000 |
| `Score/Burnout Points \| Near Miss BP` | whole number | 20 |
| `Score/Burnout Points \| Leading Race At End Of Lap BP` | whole number | 250 |
| `Score/Burnout Points \| Denied (You Were Lucky) BP` | whole number | 15 |
| `Score/Burnout Points \| Denied (Takedown Denied) BP` | whole number | 10 |
| `Score/Burnout Points \| Air Category BP` | whole number | 100 |
| `Score/Burnout Points \| Oncoming Category BP` | whole number | 100 |
| `Score/Burnout Points \| Drift Category BP` | whole number | 100 |
| `Score/Burnout Points \| Tailgate Category BP` | whole number | 5 |
| `Score/Burnout Points \| Rubbing Category BP` | whole number | 5 |
| `Score/Burnout Points \| Grinding Category BP` | whole number | 5 |
| `Score/Burnout Points \| Near Miss Category BP` | whole number | 5 |
| `Score/Burnout Points \| Take Race Position BP` | whole number | 500 |
| `Score/Burnout Points \| Double Takedown BP` | whole number | 300 |
| `Score/Burnout Points \| Takedown Spree BP` | whole number | 300 |
| `Score/Burnout Points \| Double Revenge BP` | whole number | 300 |
| `Score/Burnout Points \| Road Rage Takedown BP` | whole number | 100 |
| `Score/BP Categories \| Air Category Minima (Metres)` | decimal | 15 |
| `Score/BP Categories \| Oncoming Category Minima (Metres)` | decimal | 50 |
| `Score/BP Categories \| Drift Category Minima (Metres)` | decimal | 45 |
| `Score/BP Categories \| Tailgate Category Minima (Seconds)` | decimal | 1 |
| `Score/BP Categories \| Rubbing Category Minima (Seconds)` | decimal | 0.1 |
| `Score/BP Categories \| Grinding Category Minima (Seconds)` | decimal | 0.1 |
| `Score/BP Categories \| Near Miss Category Minima (Counts)` | decimal | 999 |
| `Score/Tailgating \| Max distance behind for tailgating (Metres)` | decimal | 15 |
| `Score/Tailgating \| Min distance behind for psyche-out when tailgating (Metres)` | decimal | 7 |
| `Score/Tailgating \| Cone angle behind for tailgating (Degrees)` | decimal | 15 |
| `Score/Tailgating \| Extra boost per second` | decimal | 15 |
| `Score/Tailgating \| Minimum tailgating time to count as tailgating (Seconds)` | decimal | 0.5 |
| `Score/Grinding \| Minimum time to grind before scoring (Seconds)` | decimal | 3 |
| `Score/Grinding \| Extra boost per second` | decimal | 15 |
| `Score/Distance Travelled \| Distance Travelled Medals (Miles)` | decimal | 4 |
| `AI/Car \| Out of range speed decrease rate` | decimal | 0 (host addition) |
| `AI/Car \| Max desDir angle change OOR` | decimal | 0 (host addition) |
| `AI/Car \| Angle you want min spd at` | decimal | 0 (host addition) |
| `AI/Car \| Top speed mps` | decimal | 0 (host addition) |
| `AI/Car \| Min speed mps` | decimal | 0 (host addition) |
| `AI/Car \| How much carAt affects steering` | decimal | 0 (host addition) |
| `AI/Car \| Angle at which drift is started` | decimal | 0 (host addition) |
| `AI/Car \| Max lock at 180 x degrees` | decimal | 0 (host addition) |
| `AI/Car \| Drift Max lock at 180 x degrees` | decimal | 0 (host addition) |
| `AI/Arbitrator \| Risk threshold` | decimal | 0 (host addition) |
| `AI/Arbitrator \| Total risk threshold` | decimal | 0 (host addition) |
| `AI/Arbitrator \| Current risk threshold` | decimal | 0 (host addition) |
| `AI/Arbitrator \| Corner Risk threshold` | decimal | 0 (host addition) |
| `AI/Arbitrator \| Total corner risk threshold` | decimal | 0 (host addition) |
| `AI/Arbitrator \| Current corner risk threshold` | decimal | 0 (host addition) |
| `AI/Avoidance \| AVOID: LookAhead dist racecars` | decimal | 0 (host addition) |
| `AI/Avoidance \| AVOID: Soft No Go offset time` | decimal | 0 (host addition) |
| `AI/Avoidance \| AVOID: Soft No Go offset distance` | decimal | 0 (host addition) |
| `AI/Avoidance \| Extra softNoGo offset dist for future` | decimal | 0 (host addition) |
| `AI/Avoidance \| Extra softNoGo offset time for future` | decimal | 0 (host addition) |
| `AI/Avoidance \| Hard No Go offset time` | decimal | 0 (host addition) |
| `AI/Avoidance \| Hard No Go offset distance` | decimal | 0 (host addition) |
| `AI/Avoidance \| Distance to discard fatally colliding racecar` | decimal | 0 (host addition) |
| `AI/Avoidance \| Vert dist to discard traffic and racecars` | decimal | 0 (host addition) |
| `AI/Avoidance \| dt between start and end vehicle` | decimal | 0 (host addition) |
| `AI/Avoidance \| Speed when car is <10m away` | decimal | 0 (host addition) |
| `AI/Avoidance \| Speed when car is <20m away` | decimal | 0 (host addition) |
| `AI/Avoidance \| Speed when car is <30m away` | decimal | 0 (host addition) |
| `AI/Avoidance \| Speed when risk is >0.95` | decimal | 0 (host addition) |
| `AI/Avoidance \| Speed when risk is >0.9` | decimal | 0 (host addition) |
| `AI/Avoidance \| Steering factor big=>extreme` | decimal | 0 (host addition) |
| `AI/Avoidance \| Aggression time variation factor` | decimal | 0 (host addition) |
| `AI/Avoidance \| Aggression dist variation factor` | decimal | 0 (host addition) |
| `AI/Avoidance \| Aggression time variation offset` | decimal | 0 (host addition) |
| `AI/Avoidance \| Aggression dist variation offset` | decimal | 0 (host addition) |
| `AI/Target \| Dist to brake speed factor big=>fast` | decimal | 0 (host addition) |
| `AI/Target \| Drift speed threshold` | decimal | 0 (host addition) |
| `AI/Target \| Dist to update target pos` | decimal | 0 (host addition) |
| `AI/Target \| Perp dist to update target pos` | decimal | 0 (host addition) |
| `AI/Target \| Corner radius to give max offset pos` | decimal | 0 (host addition) |
| `AI/Target \| Time until we hit the apex at which to start drifting (seconds)` | decimal | 0 (host addition) |
| `AI/Target \| Number of segments to extend the start of any corner` | whole number | 0 (host addition) |
| `AI/Target \| Max. number of extra segments to extend the corner based on your speed` | whole number | 0 (host addition) |
| `AI/Target \| Number of segments to extend the start of any corner (when drifting)` | whole number | 0 (host addition) |
| `AI/Target \| Max. number of extra segments to extend the corner based on your speed (when drifting)` | whole number | 0 (host addition) |
| `AI/Target \| How far away from the true apex to move the apex point of a corner when drifting (meters)` | decimal | 0 (host addition) |
| `AI/Driver \| How close the target car must be to start proper speed matching (meters)` | decimal | 0 (host addition) |
| `AI/Driver \| Maximum distance from player to start doing sticky speed matching (metres)` | decimal | 0 (host addition) |
| `AI/Driver \| Maximum diffence in speeds for sticky speed matching (MPH)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Min. aggression before we start attacking` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Min. time to wait between attacks (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Max. time to wait between attacks (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Max. distance apart to begin attacking when ahead of target (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Max. distance apart to begin attacking when behind of target (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Min. target speed to consider attacking (mph)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| How much slower than the player to drive while speed matching to attack position` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| How far in front to boost when speed matching the player` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| Extra distance in front to boost relative to aggression (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| How long to wait at the start of the race before doing aggressive driving (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving \| How long after hitting something to disable immunity (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Min time to try and block you for (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Max time to try and block you for (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Max distance ahead to start blocking you (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Preferred car separation when getting into slam position (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Max. time to try and get into slamming position (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Max. distance between cars, when ahead (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Max. difference in speeds (MPH)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Steer out distance (meters)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Steer out time (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Slam time (seconds)` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| Max. cos angle off lane to stop attack` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Slam \| How soon after starting to slam is the AI car committed and can't stop` | decimal | 0 (host addition) |
| `AI/Aggressive Driving/Reactions \| How long a rubbed AI car goes blind for (seconds)` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram Front Corner` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram Back Corner` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram Side` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram Front` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram Back` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram World` | decimal | 0 (host addition) |
| `CAD Properties \| Air Ram Low Speed Multiplier` | decimal | 0 (host addition) |
| `Crash/HandyCam \| Spring Coeff` | decimal | 0 (host addition) |
| `Crash/HandyCam \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Burnout/Position \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Burnout/Position \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Burnout/Position \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Burnout/Angular \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Burnout/Angular \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Burnout/Angular \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Shunt/Position \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Shunt/Position \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Shunt/Position \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Shunt/Angular \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Shunt/Angular \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Shunt/Angular \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Shunted/Position \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Shunted/Position \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Shunted/Position \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Shunted/Angular \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Shunted/Angular \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Shunted/Angular \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Slam/Position \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Slam/Position \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Slam/Position \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Slam/Angular \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Slam/Angular \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Slam/Angular \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Shake/Position \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Shake/Position \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Shake/Position \| Force` | decimal | 0 (host addition) |
| `InGame/Effect/Shake/Angular \| Spring Coeff` | decimal | 0 (host addition) |
| `InGame/Effect/Shake/Angular \| Damping` | decimal | 0 (host addition) |
| `InGame/Effect/Shake/Angular \| Force` | decimal | 0 (host addition) |
| `Effects/Sparks \| Size` | decimal | 0 (host addition) |
| `Effects/Shadow \| Alpha Test` | whole number | 1 (host addition) |
| `Effects/Shadow \| Opacity` | decimal | 0.7 (host addition) |
| `Effects/Shadow \| Width` | decimal | 1 (host addition) |
| `Effects/Shadow \| Length` | decimal | 1 (host addition) |
| `Effects/Shadow \| Soft Edge` | decimal | 0.1875 (host addition) |

203 values. Generated by kit_tools\make_tune_catalogue.py from the host's own catalogue.

# Reference rationale (not agent-visible)

The reference builds the conductance matrix for a small thermal graph, appends constant forcing and signed outdoor-exchange states, and propagates the coupled system over each constant-input segment. A scaled rational matrix exponential handles node state and exchange integration together. The independent test oracle uses RK4 integration of the public balance equations. The reported residual checks that stored-energy change equals heat-pump delivery, internal gains, and signed exchange with outdoors.

The heat-pump calculation derives machine effectiveness from its rated operating point, uses absolute temperatures for each reversible lift, applies the specified capacity and part-load relations, and converts interval energy to kWh. Seasonal COP is total useful heat divided by total electricity.

The independent tests cover these domain challenges:

- `NET-01` (`dynamics`): coupled node trajectories and integrated outdoor exchange, checked against independent RK4 integration.
- `NET-02` (`dynamics`): node-order invariance, disconnected components, absolute-temperature radiation, phase-transition crossing, and the first-law energy balance.
- `HP-02` (`heat_pump`): nominal rating consistency and operating-point changes in cold, part-load, and off conditions.
- `LED-03` (`state_accounting`): state continuity, interval splitting, exact record order, constitutive stored-energy/phase reporting, aggregate totals, and per-node extrema.
- `VAL-04` (`invalid_input`): invalid records reject without creating, changing, or partially publishing a report.

The runtime uses only the Python standard library. Test inputs are synthetic and constructed in the verifier; no real building telemetry or copied Modelica implementation is included.

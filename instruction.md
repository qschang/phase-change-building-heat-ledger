# Phase-change building heat ledger

A commissioning team is checking a building with several connected zones and a thermal-storage wall. During a cold-weather shift, the wall's storage behavior changes through a material transition range, while its exposed surfaces exchange heat with both outdoor air and the surrounding long-wave environment. The current command produces inconsistent temperature histories and energy totals. Repair `/app/thermal_audit.py` so a new operating record yields a trustworthy interval ledger.

Run:

```text
python3 /app/thermal_audit.py INPUT.json OUTPUT.json
```

The UTF-8 JSON input has exactly `building`, `heat_pump`, and `segments` at the top level.

`building` has exactly `nodes`, `links`, and `sigma_W_per_m2_K4`. There are 2 to 8 nodes. Each node has exactly `id` (unique nonempty string), `C_sensible_J_per_K` (positive), `latent_heat_J` (nonnegative), `transition_mid_C` (finite), `transition_width_K` (positive), `G_out_W_per_K` (nonnegative), `area_m2` (nonnegative), `T_initial_C` (finite), and `heat_fraction` (nonnegative). Node heat fractions sum to one within `1e-12`. Each link has exactly `a`, `b`, and `G_W_per_K`, names two distinct existing nodes, has positive conductance, and an unordered pair appears at most once. Disconnected zones are permitted. `sigma_W_per_m2_K4` is positive.

Each segment has exactly `duration_s`, `T_outdoor_C`, `T_radiant_C`, `T_supply_C`, `heat_command`, and `gains_W_by_node`. The gains array follows node order and contains signed watts. Segment duration is positive, the command is in `[0,1]`, and a record has 1 to 96 segments spanning no more than 86,400 seconds. Temperatures are in degrees Celsius; absolute-temperature radiation calculations use kelvins.

For node *i*, stored energy relative to 0 C is defined by the public constitutive curve:

```text
E_i(T) = C_sensible_i * T
         + latent_heat_i / 2
           * (1 + tanh((T - transition_mid_i) / transition_width_i))
```

Its effective heat capacity is the derivative of this curve with respect to temperature. During a segment, the node's energy rate is the sum of outdoor convection, long-wave radiation, linked-node conduction, allocated heat-pump output, and that node's gains:

```text
dE_i/dt = G_out_i * (T_outdoor - T_i)
           + area_i * sigma * ((T_radiant + 273.15)^4 - (T_i + 273.15)^4)
           + sum over linked j of G_ij * (T_j - T_i)
           + heat_fraction_i * Q_delivered + gains_i
```

The heat pump uses the rated reference, approaches, capacity factor, and part-load polynomial defined by the input fields `Q_nominal_W`, `COP_nominal`, `T_source_nominal_C`, `T_supply_nominal_C`, `evaporator_approach_K`, `condenser_approach_K`, `capacity_slope_per_K`, `capacity_reference_C`, and three `part_load_coefficients` `[a0,a1,a2]`. Nominal and segment source temperatures after the evaporator approach must be above absolute zero; sink temperature after the condenser approach must be above source temperature. Nominal COP is greater than one, nominal capacity is positive, and approaches are nonnegative. Reversible heating COP is sink kelvins divided by sink-source kelvins. Rated effectiveness is nominal COP divided by reversible COP at the nominal operating point. Segment COP is rated effectiveness times segment reversible COP times `a0+a1*y+a2*y*y`; that factor must be positive. Available heat is `Q_nominal_W * max(0, 1 + capacity_slope_per_K*(T_outdoor_C-capacity_reference_C))`, and delivered heat is available heat times command `y`. At zero command, interval heat/electricity are zero and COP is `null`.

The UTF-8 JSON output has exactly `intervals` and `summary`. Each interval contains `nodes` (one `{ "id", "end_C", "stored_energy_kWh", "phase_fraction" }` per input node in input order), `heat_delivered_kWh`, `electricity_kWh`, `cop`, `outdoor_exchange_kWh`, `radiant_exchange_kWh`, `building_gains_kWh`, and `thermal_balance_residual_kWh`. `stored_energy_kWh` is the constitutive stored energy relative to 0 C, converted to kWh; `phase_fraction` is the latent-transition fraction from 0 to 1 (zero when latent heat is zero). Outdoor and radiant exchange are signed positive into the building and are integrated over the interval. The residual is the total change in node stored energy minus delivered heat, gains, outdoor exchange, and radiant exchange, expressed in kWh. Its magnitude must not exceed `1e-8 kWh` per interval. Node state carries continuously between segments. The summary additionally contains `final_stored_energy_kWh`, a mapping from every node ID to its final constitutive stored energy in kWh, and `latent_storage_kWh`, the sum of latent contributions at the final state.

The summary contains sums of each interval energy/exchange/residual, `seasonal_cop` (total delivered heat divided by total electricity, or `null` when electricity is zero), and `node_extrema` mapping every node ID to `min_C` and `max_C` over its initial value and interval endpoints. State values must be within `2e-7 C`; energy and COP values must be within `1e-9` relative error with `1e-12` absolute tolerance.

All numeric values are finite numbers; booleans do not count as numbers. Invalid schemas, node properties, material parameters, links, heat allocations, operating conditions, or daily horizons exit nonzero and must not create or alter `OUTPUT.json`. The output may be published only when validation and the complete report have succeeded. The command must support newly constructed valid networks and records, not just known examples.

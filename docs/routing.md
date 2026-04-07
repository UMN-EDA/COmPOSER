---
layout: default
title: Routing
permalink: /routing/
eyebrow: Reference
description: Routing-input generation, detailed routing, and final GDS assembly in COmPOSER.
---

# Routing

In the paper, routing and PDN generation are part of the **layout synthesis** stage.

Routing in COmPOSER is split across two scripts:

- `generate_routing_inputs.py`
- `perform_routing.py`

## Step 1: Generate Routing Inputs

Command:

```bash
python3 generate_routing_inputs.py --config EXAMPLES/LNA_1/config.json
```

This script:

- reads `stage_3/placement/primitives/*.gds`
- converts each primitive GDS to a LEF macro
- writes the LEFs to `stage_3/routing/lef/`
- merges them into `<topcell>_primitives.lef`

The conversion is handled by `utils/convert_gds2lef.py`, and the merge is handled by `utils/combine_primitive_lefs.py`.

## Step 2: Run Routing and Final Assembly

Command:

```bash
python3 perform_routing.py --config EXAMPLES/LNA_1/config.json
```

This script performs three actions in order:

1. runs the Hanan router
2. generates a routed hierarchical GDS
3. runs power-grid insertion

## Paper Alignment

The attached paper describes:

- A*-based routing
- net-priority-aware routing cost
- critical nets on upper metal layers with increased widths
- PDN synthesis integrated into the flow
- user constraints such as halo spacing and critical-net labeling

That maps well to the public repo:

- `net_weights.json` prioritizes RF-critical nets
- `router_constraints.json` controls order, layers, and widths
- the Hanan router handles detailed signal routing
- `perform_power_grid_multi_level.py` adds PDN geometry after signal routing

## Inputs

- `routing.router_bin`
- `routing.routing_constraints`
- `pdk`
- `project_name/stage_3/placement/<topcell>_placement.json`
- `project_name/stage_3/routing/lef/<topcell>_primitives.lef`

## Outputs

Under `project_name/stage_3/routing/`:

- `<topcell>.def`
- `<topcell>.gds`
- `<topcell>_interim_hier.lef`
- `route.log`
- `lef/*.lef`

Under `project_name/stage_3/pdn/`:

- `<topcell>_final.gds`

## Router Constraint JSON

The example router constraint files show the main user controls:

- `do_not_route`
- `routing_order`
- per-net `preferred_layers`
- per-net `widths`

This is the main place to tell the flow:

- which nets are most important
- which nets should stay on higher metal
- which nets need wider wires
- which nets should be skipped by the signal router

## Typical Standalone Flow

If you only want to use routing after a placement already exists:

```bash
python3 generate_routing_inputs.py --config my_config.json
python3 perform_routing.py --config my_config.json
```

## PDN Step

The final PDN is added by `perform_power_grid_multi_level.py`, using:

- the routed GDS
- the `pdn` section of the main config
- the IO directions in `pad_direction`
- the power-grid layer definitions in `PDK/mock_65nm/layers.json`

That makes the routed GDS and the PDN GDS distinct outputs:

- routed geometry before power grid
- final geometry after power grid

## Post-Layout Verification Note

The paper goes one step beyond these scripts and discusses full post-layout EM and SPICE validation with possible re-synthesis. That evaluation loop is part of the paper-level methodology even though the public repo pages here focus on the open synthesis side directly exposed by the repository.

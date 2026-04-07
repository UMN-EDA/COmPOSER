---
layout: default
title: Full Flow
permalink: /flow/
eyebrow: Flow
description: End-to-end COmPOSER workflow from unsized netlist to final GDS.
---

# Full Flow

`composer.sh` is the main user-facing shell driver for the complete COmPOSER flow.

## Paper-Aligned View

The paper describes COmPOSER conceptually as:

1. hybrid analytical sizing
2. primitive block layout generation
3. layout synthesis
4. post-layout verification

The public repo implements the synthesis side of that architecture through the scripted flow below.

## Supported Modes

```bash
./composer.sh
./composer.sh <config.json>
./composer.sh <step>
./composer.sh <config.json> <step>
./composer.sh only <step>
./composer.sh <config.json> only <step>
```

Recognized steps:

- `sizing`
- `parse`
- `placement`
- `routing_inputs`
- `routing`

## What Each Step Does

### `sizing`

Runs `perform_initial_sizing.py`.

This step:

- reads the main config
- calls the stage 1 sizer specified by `stage_1_sizer`
- writes `project_name/stage_1/best_<topcell>_design.json`
- writes `project_name/stage_1/all_<topcell>_designs.csv`
- maps the chosen values into the sized netlist defined by `design.input_netlist`

### `parse`

Runs `parse_netlist.py`.

This step:

- reads the sized netlist
- parses primitive and black-box instances
- loads the datasets and surrogate models needed by primitive selection
- generates primitive GDS cells under `stage_2/primitives`
- exports `stage_2/<topcell>_design.json`
- exports `stage_2/<topcell>_nets.json`

### `placement`

Runs `perform_placement.py`.

This step:

- reads `stage_2/<topcell>_design.json`
- applies placement constraints from `placement.placement_constraints`
- solves the floorplan with Gurobi
- writes `stage_3/placement/<topcell>_placement.json`
- writes `stage_3/placement/<topcell>_placement.gds`
- copies the placed primitive GDS files into `stage_3/placement/primitives`

### `routing_inputs`

Runs `generate_routing_inputs.py`.

This step:

- converts each placed primitive GDS into LEF
- stores the individual LEFs under `stage_3/routing/lef`
- merges them into `<topcell>_primitives.lef`

### `routing`

Runs `perform_routing.py`.

This step:

- invokes the Hanan router binary on the placement JSON and combined LEF
- writes DEF, logs, and routed GDS under `stage_3/routing`
- runs `utils/gen_rt_hier_gds.py` to assemble the routed layout
- runs `perform_power_grid_multi_level.py` to add the final PDN
- writes `stage_3/pdn/<topcell>_final.gds`

## Practical Workflow

For normal use, the typical loop is:

1. Start from one of the example directories.
2. Edit `config.json`, `stage_1_config`, and the unsized netlist.
3. Set weights and placement and routing constraints.
4. Run the full flow once.
5. Re-run only the later stages while you tune placement or routing constraints.

## How This Matches the Paper

### Paper Stage 1

Maps to:

- `sizing`

### Paper Stage 2

Maps mostly to:

- `parse`

### Paper Stage 3

Maps mostly to:

- `placement`
- `routing_inputs`
- `routing`

### Paper Stage 4

The paper describes a full post-layout verification and re-synthesis loop. The public repo documents and exposes the layout-generation and synthesis side directly, and that is what this website focuses on most heavily.

## Logs

`composer.sh` creates a `logs/` directory and writes one log file per step:

- `logs/perform_initial_sizing.log`
- `logs/parse_netlist.log`
- `logs/perform_placement.log`
- `logs/generate_routing_inputs.log`
- `logs/perform_routing.log`

This makes it practical to debug a single failing stage without rerunning everything.

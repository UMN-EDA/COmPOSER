---
layout: default
title: Quickstart
permalink: /quickstart/
eyebrow: Quickstart
description: Fastest way to run COmPOSER using the included example configurations.
---

# Quickstart

The fastest way to learn the framework is to run one of the included examples exactly as provided, then inspect the generated `stage_1`, `stage_2`, and `stage_3` artifacts.

## 1. Prepare the Environment

```bash
cd COmPOSER
source .venv/bin/activate
export PROJECT_HOME="$(pwd)"
make -C ROUTER/hanan_router -j4
chmod +x composer.sh
```

## 2. Run a Full Example

LNA example:

```bash
./composer.sh EXAMPLES/LNA_1/config.json
```

PA example:

```bash
./composer.sh EXAMPLES/PA_1/config.json
```

## 3. Run from a Later Step

Start from placement onward:

```bash
./composer.sh EXAMPLES/LNA_1/config.json placement
```

Run only routing:

```bash
./composer.sh EXAMPLES/LNA_1/config.json only routing
```

## 4. Understand the Output Directory

The `project_name` in the config becomes the run directory.

For `EXAMPLES/LNA_1/config.json`, the output directory is:

```text
lna_1/
```

Inside it, the flow creates:

- `stage_1/`: best design JSON and design sweep CSV
- `stage_2/`: generated primitives plus parsed design and nets JSON
- `stage_3/placement/`: placement JSON, placement GDS, copied primitive GDS
- `stage_3/routing/`: LEF files, DEF, router log, routed GDS
- `stage_3/pdn/`: final GDS after power-grid insertion

## 5. Most Common User Edits

Before running your own design, the files you usually edit are:

- `config.json`
- the unsized input netlist in `design.input_unsized_netlist`
- `net_weights.json`
- `placement_constraint.json`
- `router_constraints.json`
- the stage 1 config JSON for your design type
- the stage 1 mapping JSON

## 6. When You Only Want One Tool

You do not need to use `composer.sh` for everything.

- Use only stage 1 sizing: `python3 perform_initial_sizing.py --config ...`
- Use only parsing and primitive generation: `python3 parse_netlist.py --config ...`
- Use only placement: `python3 perform_placement.py --config ...`
- Use only routing input generation: `python3 generate_routing_inputs.py --config ...`
- Use only routing and PDN: `python3 perform_routing.py --config ...`

The later reference pages document these standalone interfaces in more detail.

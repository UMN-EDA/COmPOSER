---
layout: default
title: Utilities
permalink: /utilities/
eyebrow: Tools
description: Utility scripts for mapping, LEF conversion, placement GDS generation, routed GDS assembly, and PDN.
---

# Utilities

Several helper scripts in this repo are useful independently from the main flow.

## `map_initial_size_to_netlist.py`

Purpose:

- append or replace instance annotations in a SPICE netlist using a stage 1 design JSON and a mapping JSON

CLI:

```bash
python3 map_initial_size_to_netlist.py \
  --netlist input.sp \
  --design-json best_design.json \
  --mapping-json stage_1_map.json \
  --output output.sp
```

This is the bridge between stage 1 sizing output and the stage 2 parser.

## `utils/convert_gds2lef.py`

Purpose:

- convert one primitive GDS into one LEF macro

CLI:

```bash
python3 utils/convert_gds2lef.py \
  --gds my_block.gds \
  --layers PDK/mock_65nm/layers.json \
  --outdir lef \
  --name my_block \
  --scale 1000 \
  --piniso
```

Use it when you want to reuse generated or external primitive GDS files with the router.

## `utils/combine_primitive_lefs.py`

Purpose:

- merge many individual LEF files into one combined LEF

CLI:

```bash
python3 utils/combine_primitive_lefs.py \
  --input_dir stage_3/routing/lef \
  --output stage_3/routing/lef/lna_primitives.lef
```

## `utils/gen_placement_gds.py`

Purpose:

- reconstruct a full placed GDS from a placement JSON file

CLI:

```bash
python3 utils/gen_placement_gds.py \
  lna_1/stage_3/placement/lna_placement.json \
  --out-gds lna_placement.gds \
  --scale 1000 \
  --copy-gds-to FINAL/PRIMITIVES
```

Useful when you want only GDS reconstruction from an already solved placement.

## `utils/gen_rt_hier_gds.py`

Purpose:

- combine routed DEF geometry with primitive GDS leaves and placement data to generate a routed GDS

CLI:

```bash
python3 utils/gen_rt_hier_gds.py \
  --pl_file lna_placement.json \
  --gds_dir stage_3/placement/primitives \
  --def_dir stage_3/routing \
  --top_cell lna \
  --layers PDK/mock_65nm/layers.json \
  --deff stage_3/routing/lna.def \
  --out stage_3/routing/lna.gds
```

This is what turns the router's DEF output into a layout database that can be opened in GDS viewers.

## `perform_power_grid_multi_level.py`

Purpose:

- add power-grid geometry to the routed GDS

Standalone CLI:

```bash
python3 perform_power_grid_multi_level.py \
  --config EXAMPLES/LNA_1/config.json \
  --infile lna_1/stage_3/routing/lna.gds \
  --top lna \
  --outfile lna_1/stage_3/pdn/lna_final.gds \
  --io-direction W N
```

The script uses:

- `pdn.pdn_width`
- `pdn.pdn_gap`
- the PDK layer stack
- the stage 2 design JSON for IO-band dimensions

## `perform_power_grid_alternate_stripes.py`

This is an alternate PDN implementation present in the repo. It is useful if you want to experiment with a different stripe-generation style without changing the main flow.

## Why These Utilities Matter

These scripts make COmPOSER modular. A user can:

- use stage 1 without using placement
- use placement without using routing
- use routing without using stage 1
- use only GDS and LEF conversion in another project

That makes the repo much more than a single monolithic automation script.

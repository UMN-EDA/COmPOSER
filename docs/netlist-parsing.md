---
layout: default
title: Netlist Parsing
permalink: /netlist-parsing/
eyebrow: Reference
description: How parse_netlist.py turns a sized SPICE netlist into generated primitives and design JSON.
---

# Netlist Parsing

`parse_netlist.py` is the main stage 2 entry point. It translates the sized netlist into layout-ready primitives plus connectivity metadata for placement and routing.

## Command

```bash
python3 parse_netlist.py --config EXAMPLES/LNA_1/config.json
```

## Required Environment

The script reads:

```bash
export PROJECT_HOME=/path/to/COmPOSER
```

This matters because some optimizer model paths are constructed relative to `PROJECT_HOME`.

## What the Parser Consumes

- `design.input_netlist`
- `design.net_weights`
- `datasets.spiral_inductor`
- `datasets.tline`
- `datasets.mimcap`
- `datasets.small_mimcap`
- `pdk`
- `pad_direction`
- `pad_mode`
- `decaps`

## What It Produces

Under `project_name/stage_2/` it writes:

- `primitives/*.gds`
- `<topcell>_design.json`
- `<topcell>_nets.json`

The design JSON contains:

- chip IO information
- module geometry variants
- pin locations
- pad metadata
- net connectivity and weights

## Primitive Types Recognized in the Netlist

The parser has direct handling for these primitive-like cell names:

- `RES`
- `CAP`
- `IND`
- `CASMOS`
- `CPWD`

Other instance types are treated as black-box or fixed primitives and are handled by copying or renaming template GDS files.

## Important Parsing Behavior

### Inductors below 100 pH

If an `IND` instance has inductance below `100` pH, the parser reclassifies it as a transmission line and routes it through the T-line flow.

### Automatic decaps

If `decaps.add_decaps` is enabled, the parser appends decap instances to the parsed subcircuit before layout generation.

### Net weights

`net_weights.json` is loaded and applied to the exported net JSON. Missing nets default to weight `1`. This is especially useful for emphasizing RF-critical paths during placement and routing.

## How Primitive Generation Happens

Inside the parser, these modules are used:

- `PRIMITIVE_GENERATORS/gen_inductor_layout.py`
- `PRIMITIVE_GENERATORS/gen_capacitor_layout.py`
- `PRIMITIVE_GENERATORS/gen_resistor_layout.py`
- `PRIMITIVE_GENERATORS/gen_bbox_layout.py`
- `PRIMITIVE_GENERATORS/gen_cpwd_layout.py`
- `PRIMITIVE_GENERATORS/gen_tline_layout.py`
- `PRIMITIVE_GENERATORS/gen_casmos_layout.py`

And these optimizers are preloaded:

- `optimize_inductor.py`
- `optimize_capacitor.py`
- `optimize_resistor.py`
- `optimize_tline.py`
- `optimize_cpwd.py`

## Black Boxes and Fixed Primitives

Some instances are not generated from scratch. Instead, they are instantiated from existing GDS assets in `FIXED_PRIMITIVES/` or other template sources.

That is how the flow supports:

- pad cells
- BGA cells
- bias blocks
- other technology- or design-specific black boxes

## Pad Modes

The parser and downstream stages support:

- `periphery`
- `bga`

In `periphery` mode, the exported chip JSON includes `io_pitch`, `io_w`, and `io_h`.

In `bga` mode, it exports BGA pitch and origin data instead.

## Why the Stage 2 JSON Matters

`perform_placement.py` and later stages do not go back to the SPICE netlist. They use the JSON exported here, so this file is the bridge between circuit intent and physical implementation.

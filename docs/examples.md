---
layout: default
title: Examples
permalink: /examples/
eyebrow: Examples
description: Meaning of the example directories and files shipped with COmPOSER.
---

# Examples

The repository includes these example designs:

- `EXAMPLES/LNA_1`
- `EXAMPLES/LNA_2`
- `EXAMPLES/LNA_3`
- `EXAMPLES/LNA_4`
- `EXAMPLES/PA_1`
- `EXAMPLES/PA_2`
- `EXAMPLES/PA_3`

Each example directory is designed to show both the user inputs and a representative set of generated outputs.

## Common Files in Each Example

| File | Meaning |
| --- | --- |
| `config.json` | Main user control file for the full flow. |
| `<design>.sp` | Unsized netlist that the user is expected to provide. |
| `<design>_optimized.sp` | Sized netlist generated after stage 1 sizing and mapping. |
| `lna_stage_1_config.json` or `pa_stage_1_config.json` | Design-class-specific constants and sweep settings for stage 1. |
| `stage_1_map.json` | Mapping from stage 1 output keys to netlist instance annotations. |
| `net_weights.json` | Net and optionally branch priorities for RF-critical connectivity. |
| `placement_constraint.json` | Placement constraints such as halo, symmetry, matching, or region restrictions. |
| `router_constraints.json` | Routing order and layer preference rules for critical nets. |
| `<project_name>/` | Generated output directory created by the flow. |

## Meaning of the Generated Subdirectory

Inside each example you will see a run directory such as `lna_1/` or `pa_1/`. This directory is created by the scripts and contains generated outputs.

Typical structure:

```text
<project_name>/
  stage_1/
  stage_2/
    primitives/
  stage_3/
    placement/
      primitives/
    routing/
      lef/
    pdn/
```

## What the Main Example Files Mean

### `config.json`

This is the main flow interface. It selects:

- which datasets are used
- which stage 1 sizer is used
- which design files are used
- where outputs are written
- which PDK is used
- which placement, routing, and PDN settings are applied

### `*.sp`

This is the unsized input netlist. Users are expected to provide a netlist with the same primitive naming conventions and annotation style expected by the parser and mapping scripts.

### `*_optimized.sp`

This is the stage 1 output netlist after the best sizing result has been mapped back into the original netlist instances.

### Stage 1 config JSON

This stores the design-class-specific constants used by the equation-based stage 1 sizer. LNA and PA examples use different files because their sizing logic is different.

### `net_weights.json`

This file lets users prioritize RF-critical nets. In LNA examples it may also include `branches`, which helps preserve weighting on especially important point-to-point RF paths.

### `placement_constraint.json`

Users can add:

- `halo`
- `keepouts`
- `symmetry`
- `alignment`
- `regions`
- `proximity`
- `ordering`

The shipped examples are intentionally light, but the placer supports richer constraint patterns than the simplest example files show.

### `router_constraints.json`

This file is the user's routing-control interface. It can express:

- nets that should not be routed
- routing priority order
- per-net preferred layers
- per-net width overrides
- other router non-default rules supported by the Hanan router input format

## Example-Specific Pattern

The LNA examples are built around a cascode-style LNA flow and typically include:

- gate, source, and drain inductors
- CPWD input structures
- MOS and bias black boxes

The PA examples are built around stage-based PA sizing and matching networks and typically include:

- stage transistor blocks
- shunt and series matching capacitors
- inductive matching structures
- power and output routing emphasis

## How This Aligns with the Paper

The paper reports results on:

- four LNAs
- three PAs

That same split is reflected in this repo's public examples:

- `LNA_1` to `LNA_4`
- `PA_1` to `PA_3`

So these directories are not arbitrary demos. They line up with the paper's design classes and validation story, making them the right starting point when you want the website and the paper to tell a consistent story.

## How to Use the Examples

Best practice is:

1. Copy the closest example directory.
2. Rename the internal paths and `project_name`.
3. Replace the unsized netlist.
4. Replace the stage 1 config and mapping file only if your design class changes.
5. Update the constraints and weights to match your own RF priorities.

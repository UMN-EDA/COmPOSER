---
layout: default
title: Placement
permalink: /placement/
eyebrow: Reference
description: Gurobi-based floorplanning and placement constraints in COmPOSER.
---

# Placement

In the paper, placement is part of the **layout synthesis** stage.

`perform_placement.py` reads the parsed stage 2 design JSON and produces the placed layout.

## Command

```bash
python3 perform_placement.py --config EXAMPLES/LNA_1/config.json
```

## Inputs

- `project_name/stage_2/<topcell>_design.json`
- `placement.placement_constraints`
- `placement.timelimit`
- `placement.aspect_ratio`
- `placement.level`
- `placement.weight_hpwl`
- `placement.plot_html`

## Outputs

Under `project_name/stage_3/placement/`:

- `<topcell>_placement.json`
- `<topcell>_placement.gds`
- `primitives/*.gds`

If enabled, the script can also generate an interactive `floorplan.html`.

## Paper Alignment

The paper explicitly frames placement as a **MILP-based placement** problem with area and weighted-HPWL objectives, halo-aware non-overlap, and extra emphasis on user-labeled RF-critical nets.

That matches the public implementation here:

- placement is solved with Gurobi
- per-net weights affect the HPWL term
- halo spacing is a first-class user control
- module variants and rotations are selectable
- IO placement constraints are part of the formulation

## Solver

The placer uses Gurobi. The placement JSON it produces is the key input to routing.

## Supported Constraint Types

The `Constraints` class in `perform_placement.py` supports:

- `halo`
- `keepouts`
- `symmetry`
- `alignment`
- `regions`
- `proximity`
- `ordering`

The shipped example files only show a minimal `halo` example, but the code supports a much richer constraint set.

## Constraint File Examples

### Minimal halo

```json
{
  "halo": 1000
}
```

### Supported richer structure

The code accepts structures such as:

- keepout rectangles using `ll` and `ur`
- symmetry groups using `modules` or explicit `pairs`
- alignment groups such as `top`, `bottom`, `left`, `right`, `center_x`, `center_y`
- region constraints keyed by module name

That makes the placement JSON the right place to encode:

- matching intent
- symmetry intent
- analog layout grouping
- keepout areas
- placement ordering preferences

## Pad Handling

The placer handles both:

- periphery IO placement
- BGA IO placement

In periphery mode it reserves edge bands and snaps pads to the legal IO pitch.

In BGA mode it snaps pad centers to a BGA lattice using the pitch information from the PDK or chip JSON.

## Why the Paper Emphasis Matters

The paper's argument is that RF/mm-wave performance is tightly coupled to layout choices. That is why this site now treats placement as part of the synthesis method itself, not as a generic downstream implementation detail.

## What the Placement JSON Contains

The exported `<topcell>_placement.json` includes:

- final chip width and height
- placed module coordinates
- chosen orientation
- active GDS file for the chosen variant
- transformed pin locations

This becomes the direct input to both routing and final GDS assembly.

## Standalone Use

If you already have a valid stage 2 design JSON, you can use the placer without running stage 1 again.

That makes it useful for:

- rapid floorplan exploration
- testing new placement constraints
- benchmarking only the physical-placement stage

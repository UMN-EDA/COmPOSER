---
layout: default
title: Primitives
permalink: /primitives/
eyebrow: Reference
description: Fixed primitives, primitive generators, primitive optimizers, and mock PDK assets.
---

# Primitives

COmPOSER's primitive ecosystem combines four things:

1. fixed GDS black boxes
2. parametric primitive generators
3. data-driven primitive optimizers
4. a mock PDK definition used by layout-generation scripts

## Fixed Primitives

The `FIXED_PRIMITIVES/` directory currently contains:

- `pad.gds`
- `bga.gds`
- `nmos_bias_1.gds`
- `auto_gen_decap_lna_0_1.gds`

These are treated as black boxes by the flow. They are useful for:

- pads
- BGA IO
- biasing blocks
- decap placeholders

For real use, users can substitute technology-specific black-box layouts while keeping the same top-level integration pattern.

## Mock PDK

`PDK/mock_65nm/layers.json` is the flow's layer and rule source.

It defines:

- layer names and GDS numbers
- draw, pin, label, and blockage datatypes
- routing widths and pitches
- via rules
- top and bottom routing layers
- power-grid layer preferences
- pad pitch information for periphery and BGA modes

This lets the full flow run without a proprietary PDK, but it should be treated as a mock or paired dummy PDK, not a tapeout-ready technology file.

## Primitive Generators

These scripts can be used inside the full flow or standalone.

### `gen_inductor_layout.py`

Use for:

- octagonal spiral inductors
- symmetric inductors
- patterned ground shield options
- dummy routing-friendly output

Example:

```bash
python3 PRIMITIVE_GENERATORS/gen_inductor_layout.py \
  --pdk PDK/mock_65nm/layers.json \
  --name gate_ind \
  --type std \
  --num-turns 2 \
  --inner_radius 50 \
  --clearance 5 \
  --width 5
```

### `gen_capacitor_layout.py`

Use for:

- MIM capacitor generation
- small-cap generation

Example:

```bash
python3 PRIMITIVE_GENERATORS/gen_capacitor_layout.py \
  --pdk PDK/mock_65nm/layers.json \
  --len 10 \
  --wid 10
```

### `gen_resistor_layout.py`

Use for poly resistor layout generation.

```bash
python3 PRIMITIVE_GENERATORS/gen_resistor_layout.py \
  --pdk PDK/mock_65nm/layers.json \
  --length 20 \
  --width 2 \
  --name poly_res_1 \
  --output_dir PRIMITIVE_GENERATORS/examples
```

### `gen_tline_layout.py`

Use for straight transmission-line primitives.

```bash
python3 PRIMITIVE_GENERATORS/gen_tline_layout.py \
  --pdk PDK/mock_65nm/layers.json \
  --length 200 \
  --width 4 \
  --output_gds_name t_line_demo
```

### `gen_cpwd_layout.py`

Use for CPWD generation from length, width, and gap.

```bash
python3 PRIMITIVE_GENERATORS/gen_cpwd_layout.py \
  --pdk PDK/mock_65nm/layers.json \
  --length 100 \
  --width 12 \
  --gap 2 \
  --output_gds_name cpwd_demo
```

### `gen_casmos_layout.py`

Use for generated CASMOS device geometry.

```bash
python3 PRIMITIVE_GENERATORS/gen_casmos_layout.py \
  --pdk PDK/mock_65nm/layers.json \
  --length 0.06 \
  --finger_width 1 \
  --number_of_fingers 22 \
  --output_gds_name casmos_demo
```

### `gen_bbox_layout.py`

Use when you already have a black-box GDS and only need:

- a new cell name
- a new instance-specific output file
- shifting to origin

```bash
python3 PRIMITIVE_GENERATORS/gen_bbox_layout.py \
  --input_gds FIXED_PRIMITIVES/pad.gds \
  --output_dir PRIMITIVE_GENERATORS/examples \
  --output_gds_name RF_IN1.gds \
  --new_name RF_IN1
```

## Primitive Optimizers

These scripts predict geometry from electrical targets or train the surrogate models used by the parser.

For the data-driven scripts, set:

```bash
export PROJECT_HOME="$(pwd)"
```

### `optimize_inductor.py`

Inverse-design helper for inductors using kNN plus an EM surrogate.

Example:

```bash
python3 PRIMITIVE_OPTIMIZERS/optimize_inductor.py \
  --dataset_path DATASETS/spiral_ind_data.csv \
  --inductance 1700 \
  --peak_q 20 \
  --srf 80
```

### `optimize_capacitor.py`

Polynomial capacitor model for:

- forward capacitance prediction
- inverse search for candidate dimensions

Example:

```bash
python3 PRIMITIVE_OPTIMIZERS/optimize_capacitor.py \
  --csv_path DATASETS/mimcap_dataset.csv \
  --target_cap 505 \
  --degree 2 \
  --export_equation
```

### `optimize_resistor.py`

Simple geometric search for resistor dimensions that meet a target resistance.

Example:

```bash
python3 PRIMITIVE_OPTIMIZERS/optimize_resistor.py \
  --R_target 1000 \
  --W_min 0.8 \
  --W_max 10 \
  --L_min 0.8 \
  --L_max 100
```

### `optimize_tline.py`

kNN-based transmission-line geometry predictor from inductance.

Example:

```bash
python3 PRIMITIVE_OPTIMIZERS/optimize_tline.py \
  --csv_path DATASETS/tline_data.csv \
  --query_point 100 \
  --n_neighbors 3
```

### `optimize_cpwd.py`

CPWD geometry prediction from electrical descriptors.

Example:

```bash
python3 PRIMITIVE_OPTIMIZERS/optimize_cpwd.py \
  --csv-path DATASETS/cpwd_data.csv \
  --beta-l 0.023 \
  --char-imp 18 \
  --n-neighbors 500
```

### `emx_estimator.py`

Trains or loads the inductor EM surrogate model.

Example:

```bash
python3 PRIMITIVE_OPTIMIZERS/emx_estimator.py
```

## Included Primitive Output Examples

The repository also includes sample generated primitive GDS files under `PRIMITIVE_GENERATORS/examples/`, such as:

- `cap.gds`
- `small_cap.gds`
- `poly_res.gds`
- `t_line.gds`
- `cpwd.gds`
- `inductor.gds`
- `casmos.gds`
- `pad_out.gds`

These are useful as quick visual references for what the standalone generators emit.

## Standalone Primitive Flow

If you want only the primitive subsystem in your own project, a typical usage pattern is:

1. prepare your own datasets with identical schema
2. train or load the surrogate models
3. call the optimizer for the target electrical value
4. pass the chosen geometry to the corresponding generator
5. export the resulting GDS into your own flow

That standalone workflow is one of the strongest reusable parts of this repository.

---
layout: default
title: Stage 1 Sizing
permalink: /stage-1-sizing/
eyebrow: Reference
description: Equation-based stage 1 sizing flow for LNA and PA examples.
---

# Stage 1 Sizing

In the paper, this is the **hybrid analytical sizing** stage.

Stage 1 converts high-level electrical targets into an initial sized netlist.

It is driven by:

- `perform_initial_sizing.py`
- a design-class-specific sizer such as `lna_stage_1_sizer.py` or `pa_stage_1_sizer.py`
- `map_initial_size_to_netlist.py`
- the per-design `stage_1_map.json`

## Main Driver

```bash
python3 perform_initial_sizing.py --config EXAMPLES/LNA_1/config.json
```

This script:

1. reads the main config
2. calls the configured stage 1 sizer
3. writes a best-design JSON and a sweep CSV into `project_name/stage_1/`
4. maps the chosen values into `design.input_netlist`

## Paper Alignment

The paper describes this stage as coupling closed-form circuit equations with ML-based EM refinement so that the selected sizes are already more layout-aware than a purely schematic-only flow.

That is the right mental model for the public scripts here too:

- analytical equations drive the first sizing pass
- passive selection depends on learned or surrogate models
- the result is then mapped into a sized netlist for physical synthesis

## LNA Stage 1

Example entry point:

```text
lna_stage_1_sizer.py
```

The LNA sizer reads:

- `design_requirements.freq_ghz`
- `design_requirements.nf_req_db`
- `design_requirements.gain_req_db`
- `design_requirements.bw_req_ghz`
- `design_requirements.s11_req_db`
- `design_requirements.pwr_req_mw`
- `datasets.spiral_inductor`
- `datasets.cpwd`
- the JSON pointed to by `stage_1_config`

### LNA stage 1 config sections

The example `EXAMPLES/LNA_1/lna_stage_1_config.json` is organized into:

- `model_settings`
- `debug`
- `device_constants`
- `unit_conversions`
- `formula_constants`
- `sweeps`
- `thresholds`
- `fallbacks`
- `interstage`
- `s11_reference`
- `scoring`

This is where the user tunes the equation-based sizing model itself. It is not the same as the top-level `config.json`.

### LNA outputs

The LNA sizer writes:

- `best_lna_design.json`
- `all_lna_designs.csv`

The best-design JSON contains the selected values that stage 1 mapping consumes, including:

- MOS sizing
- gate, source, and drain inductor values
- CPWD geometry
- predicted design metrics and selection score

## PA Stage 1

Example entry point:

```text
pa_stage_1_sizer.py
```

The PA sizer reads:

- `design_requirements.freq_ghz`
- `design_requirements.gain_req_db`
- `design_requirements.p_sat_db`
- `datasets.spiral_inductor`
- the PA stage 1 config JSON

### PA stage 1 config sections

The example `EXAMPLES/PA_1/pa_stage_1_config.json` is flatter than the LNA version. It contains:

- device constants such as `cgs`, `cd`, `gm`, `rgate`, `vdsat`, `ft`
- output-stage sizing constants
- matching-network calculation constants
- optimizer behavior switches such as `optimizer_four_variants`

### PA outputs

The PA sizer writes:

- `best_pa_design.json`
- `pa_designs.csv`

These results include stage sizes and matching-element targets, which are later mapped into the PA netlist.

## Mapping Stage 1 Results into the Netlist

`map_initial_size_to_netlist.py` is the bridge between stage 1 JSON output and the actual SPICE netlist annotations.

CLI:

```bash
python3 map_initial_size_to_netlist.py \
  --netlist EXAMPLES/LNA_1/lna_1.sp \
  --design-json lna_1/stage_1/best_lna_design.json \
  --mapping-json EXAMPLES/LNA_1/stage_1_map.json \
  --output EXAMPLES/LNA_1/lna_1_optimized.sp
```

### Supported mapping modes

`stage_1_map.json` supports two modes.

#### `json_list`

Use a list of keys directly from the stage 1 design JSON.

Typical use:

- inductors
- capacitors
- CPWD parameters

#### `regex_extract`

Extract numbers from a formatted string value such as a MOS sizing string.

Typical use:

- `CASMOS_Size`
- PA stage-size strings

## Why Stage 1 Matters

Stage 2 and stage 3 assume the netlist already contains usable physical target annotations. If the stage 1 mapping is wrong, the parser will generate the wrong primitives or fail to interpret the intended devices.

# PRIMITIVE_GENERATORS

This directory contains the standalone layout generators and supporting utilities used to create primitive GDS cells for the RF design automation flow.

The generators in this directory are intended to produce reusable layout building blocks such as inductors, capacitors, resistors, transmission lines, CPW structures, pads, and device-level primitives. These generated layouts can then be consumed by downstream placement, routing, and layout assembly scripts.

---

## Overview

Each generator is designed around a specific primitive type and typically accepts geometry parameters together with a required PDK `layers.json` file. The PDK file provides the layer numbers, datatypes, label layers, and via enclosure rules needed to produce technology-consistent GDS output.

In general, the command-line flow for a generator is:

```bash
python <generator_script>.py --pdk /path/to/layers.json [other options]
```

Most generators write their output GDS directly to a user-specified directory. Several generators also create an internal helper cell and then export a top-level wrapper cell aligned to the origin for easier downstream use.

---

## Common Requirements

Before running the generators, make sure the following are available:

- A Python environment with required packages such as `gdspy`, `numpy`, `pandas`, or any script-specific dependencies.
- A valid PDK `layers.json` file.
- Read and write access to the target output directory.

Typical PDK argument example:

```bash
--pdk /path/to/pdk/rf_65_pdks/65n_placer/layers.json
```

---

## Generators and Use Cases

### 1. `gen_inductor_layout.py`

Generates octagonal spiral inductors for RF layout generation.

#### Use cases

- Standard spiral inductor generation
- Symmetric spiral inductor generation
- Optional patterned ground shield generation
- Optional routing-friendly dummy GDS generation for layout automation flows

#### Supported modes

- `std` for standard inductors
- `sym` for symmetric inductors

#### Command format

```bash
python gen_inductor_layout.py --pdk /path/to/layers.json [options]
```

#### Example commands

Standard inductor:

```bash
python gen_inductor_layout.py \
  --pdk /path/to/layers.json \
  --type std \
  --name inductor_1 \
  --num-turns 2 \
  --num-sides 8 \
  --inner_radius 50 \
  --clearance 5 \
  --width 5
```

Symmetric inductor:

```bash
python gen_inductor_layout.py \
  --pdk /path/to/layers.json \
  --type sym \
  --name inductor_sym_1 \
  --num-turns 2 \
  --num-sides 8 \
  --inner_radius 50 \
  --clearance 5 \
  --width 5
```

With routing dummy output:

```bash
python gen_inductor_layout.py \
  --pdk /path/to/layers.json \
  --name inductor_route \
  --gen_routing \
  --output_real output_gds_real \
  --output_dummy output_gds_dummy
```

---

### 2. `gen_capacitor_layout.py`

Generates capacitor primitives, including an interdigitated-style MIM capacitor and a small MIM capacitor variant.

#### Use cases

- Interdigitated or structured MIM capacitor generation
- Small MIM capacitor generation
- Primitive generation for analog and RF blocks that require prebuilt capacitor cells

#### Command format

```bash
python gen_capacitor_layout.py --pdk /path/to/layers.json [options]
```

#### Example command

```bash
python gen_capacitor_layout.py \
  --pdk /path/to/layers.json \
  --len 10 \
  --wid 10
```

#### Notes

This script is structured so that a single run can generate both capacitor variants and write them into the current working directory with predefined output names such as `cap.gds` and `small_cap.gds`.

---

### 3. `gen_resistor_layout.py`

Generates a poly resistor primitive.

#### Use cases

- Fixed resistor primitive generation
- Creation of parameterized resistor cells for schematic-to-layout flows
- Reusable resistor blocks for analog automation

#### Command format

```bash
python gen_resistor_layout.py --pdk /path/to/layers.json [options]
```

#### Example command

```bash
python gen_resistor_layout.py \
  --pdk /path/to/layers.json \
  --length 20 \
  --width 2 \
  --name poly_res_1 \
  --output_dir PRIMITIVES
```

---

### 4. `gen_bbox_layout.py`

Creates an instance-specific black box (bbox) GDS from an existing black box template GDS.

#### Use cases

- Reusing a fixed bbox template across many different pad instances
- Renaming the top cell to an instance-specific name
- Exporting pad GDS files into a primitive library directory

#### What it does

This script does not synthesize a pad from scratch. Instead, it reads an input pad GDS, creates an output version with a user-provided output name, and is intended to support bbox instantiation workflows in parser and primitive-generation flows.

#### Command format

```bash
python gen_bbox_layout.py --input_gds <pad_template.gds> --output_dir <dir> [options]
```

#### Example command

```bash
python gen_bbox_layout.py \
  --input_gds FIXED_PRIMITIVES/pad.gds \
  --output_dir PRIMITIVES \
  --output_gds_name RF_IN1.gds \
  --new_name RF_IN1
```

---

### 5. `gen_tline_layout.py`

Generates a transmission line primitive with labeled ports.

#### Use cases

- Straight transmission line generation
- RF interconnect primitive generation
- Reusable line structures for passive layout flows

#### Command format

```bash
python gen_tline_layout.py --pdk /path/to/layers.json [options]
```

#### Example command

```bash
python gen_tline_layout.py \
  --pdk /path/to/layers.json \
  --length 200 \
  --width 4 \
  --output_dir PRIMITIVES \
  --output_gds_name tline_1
```

---

### 6. `gen_cpwd_layout.py`

Generates a coplanar waveguide with ground conductors and labeled ports.

#### Use cases

- CPW-based routing primitive generation
- RF passive layout generation where ground-return structures are needed
- Reusable coplanar structures for RF design automation

#### Command format

```bash
python gen_cpwd_layout.py --pdk /path/to/layers.json [options]
```

#### Example command

```bash
python gen_cpwd_layout.py \
  --pdk /path/to/layers.json \
  --length 200 \
  --width 10 \
  --gap 3 \
  --output_dir PRIMITIVES \
  --output_gds_name cpwd_1
```

---

### 7. `gen_casmos_layout.py`

Generates a CASMOS-style transistor-level device layout structure.

#### Use cases

- Parameterized active device primitive generation
- Structured transistor layout construction for reusable device-level cells
- Automated generation of RF or analog device macros

#### Command format

```bash
python gen_casmos_layout.py --pdk /path/to/layers.json [options]
```

#### Example command

```bash
python gen_casmos_layout.py \
  --pdk /path/to/layers.json \
  --length 0.06 \
  --finger_width 1.0 \
  --number_of_fingers 22 \
  --dummy 2 \
  --output_dir PRIMITIVES \
  --output_gds_name casmos_1
```

---

## Recommended Directory Usage

A typical flow is to generate all primitive cells into a dedicated output directory such as:

```bash
PRIMITIVES/
```

For example:

```bash
python gen_resistor_layout.py --pdk /path/to/layers.json --name R1 --output_dir PRIMITIVES
python gen_tline_layout.py --pdk /path/to/layers.json --output_gds_name TL1 --output_dir PRIMITIVES
python gen_bbox_layout.py --input_gds FIXED_PRIMITIVES/pad.gds --output_dir PRIMITIVES --output_gds_name RF_IN1.gds --new_name RF_IN1
```

This keeps the generated primitive library organized and makes it easier for parser, placer, and router scripts to consume the produced GDS cells.

---

## Notes

- Many generators rely on the same PDK layer metadata and via rules, so consistent use of the correct `layers.json` file is important.
- Output GDS names should usually match the intended primitive instance or reusable cell name.
- When generating large primitive libraries, it is good practice to keep output names deterministic and directory structure consistent.

---

## Summary

The `PRIMITIVE_GENERATORS` directory provides the core primitive layout generation capability for the RF design automation flow. It enables parameterized creation of reusable passive, active, and interface building blocks that can be composed later during automated layout generation.


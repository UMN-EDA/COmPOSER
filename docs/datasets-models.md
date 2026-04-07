---
layout: default
title: Datasets and Models
permalink: /datasets-models/
eyebrow: Data
description: Reference dataset schemas and model expectations in COmPOSER.
---

# Datasets and Models

The primitive optimizers depend on CSV datasets and locally stored trained model files.

## Critical Rule

The datasets shipped in this repository are reference-format datasets. They are not intended to be your final production datasets.

Users should generate their own datasets for their own process, simulator, extraction flow, and technology assumptions, while keeping:

- the same column names
- the same semantic meaning
- the same units

If the headers or units change, the optimization scripts can fail or return misleading geometry selections.

## Reference Datasets in `DATASETS/`

| File | Purpose |
| --- | --- |
| `spiral_ind_data.csv` | Spiral inductor geometry and EM-performance reference dataset. |
| `tline_data.csv` | Transmission-line reference dataset. |
| `mimcap_dataset.csv` | Main MIM capacitor reference dataset. |
| `small_mimcap_dataset.csv` | Small-capacitor reference dataset used by the parser. |
| `cpwd_data.csv` | CPWD reference dataset for characteristic impedance and phase behavior. |

## Required Columns and Units

### Spiral inductors

| Column | Meaning | Unit |
| --- | --- | --- |
| `Radius` | Spiral radius | `um` |
| `Width` | Metal width | `um` |
| `Gnd dist` | Ground distance | `um` |
| `Spacing` | Metal spacing | `um` |
| `Turns` | Number of turns | count |
| `Inductance` | Inductance | `pH` |
| `Peak Q` | Peak quality factor | unitless |
| `Peak Q Freq` | Frequency at peak Q | `GHz` |
| `SRF` | Self-resonant frequency | `GHz` |

### Transmission lines

| Column | Meaning | Unit |
| --- | --- | --- |
| `Length` | Line length | `um` |
| `Width` | Line width | `um` |
| `Inductance` | Inductance | `pH` |
| `Peak Q` | Peak quality factor | unitless |
| `Peak Q Freq` | Frequency at peak Q | `GHz` |
| `SRF` | Self-resonant frequency | `GHz` |

### MIM capacitors

| Column | Meaning | Unit |
| --- | --- | --- |
| `Length` | Capacitor length | `um` |
| `Width` | Capacitor width | `um` |
| `Aspect Ratio` | Length-to-width ratio | unitless |
| `Capacitance` | Capacitance | `fF` |
| `Area` | Physical area | `um2` |

### Small MIM capacitors

| Column | Meaning | Unit |
| --- | --- | --- |
| `Length` | Capacitor length | `um` |
| `Width` | Capacitor width | `um` |
| `Capacitance` | Capacitance | `fF` |

The unit interpretation for `small_mimcap_dataset.csv` is inferred from the surrounding capacitor flow and from the main MIM capacitor dataset.

### CPWD

| Column | Meaning | Unit |
| --- | --- | --- |
| `Length` | CPWD length | `um` |
| `Width` | Center conductor width | `um` |
| `Gap` | CPWD gap | `um` |
| `Char_Imp` | Characteristic impedance | `ohms` |
| `beta_l` | Phase-length term | model-specific scalar |
| `root_er` | Effective dielectric term | model-specific scalar |

## Model Files in `MODELS/`

The `MODELS/` directory is intended to store serialized `.pkl` models for reuse. The committed README explicitly notes that the actual `.pkl` files are not checked in.

Typical model roles in this repo:

- inductor EM surrogate
- inductor inverse-design kNN helper
- capacitor polynomial surrogate

This keeps iterative optimization fast by avoiding retraining during every run.

## Practical Guidance

- Keep your generated CSVs numerically clean.
- Do not silently change units.
- Keep header spelling exact, including spaces and capitalization.
- If your process uses different units internally, convert before writing the CSV.

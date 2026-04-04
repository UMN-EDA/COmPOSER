# Datasets Directory

This directory contains reference CSV datasets used by the primitive optimization workflows in **COmPOSER**.

The dataset files in this repository are intended primarily as **format references**. In practical use, users are expected to **generate their own datasets locally** using their own technology setup, process assumptions, simulation environment, and extraction flow.

## Important Requirement

All user-generated datasets must follow the **same CSV structure**, **same header names**, and **same units** expected by the optimization scripts.

This is important because the downstream model-training and optimization utilities read columns by their exact names. Any mismatch in column headers, missing fields, reordered meaning, or inconsistent units can break the workflow or produce incorrect model behavior.

## Current Directory Contents

The current repository directory contains the following reference datasets:

- `mimcap_dataset.csv`
- `spiral_ind_data.csv`
- `tline_data.csv`

These files define the expected schema for capacitor, spiral inductor, and transmission-line data, respectively. ?cite?turn185911view0?

## General Dataset Guidelines

When generating your own data, make sure that:

- The **column names match exactly**.
- The **units remain consistent** with the expected format.
- Each row corresponds to one valid simulated or extracted primitive instance.
- The data is numerically clean and free of missing or malformed values.
- The same naming convention is preserved across the entire dataset.

## Expected File Formats

### 1. Transmission Line Dataset

The transmission-line dataset must use the following CSV headers and units:

| Column Name | Meaning | Unit |
|---|---|---|
| `Length` | Transmission line length | `um` |
| `Width` | Transmission line width | `um` |
| `Inductance` | Inductance | `pH` |
| `Peak Q` | Peak quality factor | unitless |
| `Peak Q Freq` | Frequency at peak Q | `GHz` |
| `SRF` | Self-resonant frequency | `GHz` |

Recommended header order:

```text
Length,Width,Inductance,Peak Q,Peak Q Freq,SRF
```

Equivalent unit interpretation:

```text
Length(um), Width(um), Inductance(pH), Peak Q, Peak Q Freq(GHz), SRF(GHz)
```

### 2. Spiral Inductor Dataset

The spiral inductor dataset must use the following CSV headers and units:

| Column Name | Meaning | Unit |
|---|---|---|
| `Radius` | Spiral radius | `um` |
| `Width` | Metal width | `um` |
| `Gnd dist` | Ground distance | `um` |
| `Spacing` | Metal spacing | `um` |
| `Turns` | Number of turns | `#` |
| `Inductance` | Inductance | `pH` |
| `Peak Q` | Peak quality factor | unitless |
| `Peak Q Freq` | Frequency at peak Q | `GHz` |
| `SRF` | Self-resonant frequency | `GHz` |

Recommended header order:

```text
Radius,Width,Gnd dist,Spacing,Turns,Inductance,Peak Q,Peak Q Freq,SRF
```

Equivalent unit interpretation:

```text
Radius (um), Width(um), Gnd dist(um), Spacing(um), Turns (#), Inductance(pH), Peak Q, Peak Q Freq(GHz), SRF(GHz)
```

### 3. Capacitor Dataset

The capacitor dataset must use the following CSV headers and units:

| Column Name | Meaning | Unit |
|---|---|---|
| `Length` | Capacitor length | `um` |
| `Width` | Capacitor width | `um` |
| `Aspect Ratio` | Ratio of length to width | unitless |
| `Capacitance` | Capacitance | `fF` |
| `Area` | Physical area | `um2` |

Recommended header order:

```text
Length,Width,Aspect Ratio,Capacitance,Area
```

Equivalent unit interpretation:

```text
Length(um), Width(um), Aspect Ratio(Length/Width), Capacitance(fF), Area(um2)
```

## Notes on Consistency

A few points are especially important when preparing custom datasets:

### Header Names Must Match Exactly

Use the exact header names expected by the scripts. For example:

- Use `Peak Q Freq`, not `Peak_Q_Freq`
- Use `Gnd dist`, not `Ground Distance`
- Use `Aspect Ratio`, not `AR`

### Units Must Be Kept Consistent

Do not mix units across datasets. For example:

- If inductance is expected in `pH`, do not provide it in `nH`
- If frequency is expected in `GHz`, do not provide it in `MHz`
- If dimensions are expected in `um`, do not provide them in `nm`

If your raw simulation data uses different units, convert it before saving the CSV.

### Data Quality Matters

Since these datasets are used for model fitting, neighbor search, and geometry prediction, poor-quality data can directly degrade optimization quality. Use physically valid, consistently generated simulation data and verify that each row is meaningful before training models on it.

## Recommended Workflow

A typical workflow is:

1. Generate primitive data locally using your own simulation or extraction flow.
2. Export the results into CSV files using the required header names and units.
3. Place the generated CSV files in this directory or point the optimization scripts to their location.
4. Train the corresponding models locally using these datasets.
5. Use the trained models in the primitive optimization flow.

## Repository Note

The datasets present in this directory should be treated as examples or schema references for the expected input format. Users should regenerate datasets appropriate to their own design environment and maintain strict compatibility with the required CSV structure.


# PRIMITIVE_OPTIMIZERS

This directory contains the primitive-level optimization utilities used by the COmPOSER flow. These scripts support geometry selection for individual passive and EM-driven primitives before layout generation. In general, the optimizers map between **electrical targets** and **physical dimensions** using either analytical expressions, k-nearest-neighbor search, or trained surrogate models.

The directory mixes two types of files:

- **User-facing optimizers** that can be run directly from the command line.
- **Support modules** that train or load surrogate models used by the higher-level optimizers.

---

## Directory Contents

The directory currently contains the following files:

- `__init__.py`
- `emx_estimator.py`
- `knn_with_emx_estimator_geom_predictor.py`
- `optimize_capacitor.py`
- `optimize_inductor.py`
- `optimize_resistor.py`
- `optimize_tline.py`

---

## What This Directory Is Used For

These scripts are intended to answer questions of the following form:

- Given a target capacitance, what capacitor dimensions are reasonable?
- Given a target resistance, what resistor dimensions are feasible?
- Given a target inductance or a fuller inductor specification tuple, what geometry is likely to meet it?
- Given a target transmission-line inductance, what line dimensions should be proposed?

For the more data-driven cases, the optimization flow uses pre-trained or auto-generated surrogate models so that repeated optimization runs can be executed quickly inside iterative design loops.

---

## Environment and Dependencies

Most scripts in this directory assume that `PROJECT_HOME` is defined and points to the repository root. Several default dataset and model paths are constructed relative to:

```bash
$PROJECT_HOME/DEV/
```

Typical Python dependencies used across this directory include:

- `numpy`
- `pandas`
- `scikit-learn`
- `scipy`
- `joblib`
- `matplotlib`
- `plotly`

A typical setup is:

```bash
export PROJECT_HOME=/path/to/COmPOSER
```

---

## File-by-File Description

## `__init__.py`

Marks `PRIMITIVE_OPTIMIZERS` as a Python package so the individual optimizers and helper modules can be imported from other scripts.

**Typical use case**

- Package import support only.

---

## `emx_estimator.py`

Trains or loads a **RandomForest-based EM surrogate model** for inductor prediction. The model maps geometry parameters:

- `Radius`
- `Width`
- `Spacing`
- `Turns`

into predicted EM/specification outputs:

- `Inductance`
- `Peak Q`
- `Peak Q Freq`
- `SRF`

It also contains utilities for model evaluation, result export, and optional PDF plot generation.

**Primary role**

- Support module for inductor optimization.
- Trains and reuses the EM surrogate stored under the models directory.

**Generated artifact**

- `DEV/MODELS/emx_rf_model.pkl`

**Typical use cases**

- Train the EM surrogate once and reuse it later.
- Predict EM/spec values from a proposed inductor geometry.
- Serve as the forward model used inside `optimize_inductor.py`.

**Standalone usage**

The script includes a simple example `__main__` block that trains using a default CSV in the current working directory.

```bash
python emx_estimator.py
```

**Programmatic usage**

```python
from PRIMITIVE_OPTIMIZERS import emx_estimator

model = emx_estimator.train_emx_estimator(dataset_path)
preds = emx_estimator.infer_emx_model([[100, 10, 2, 3.0]], model)
```

---

## `knn_with_emx_estimator_geom_predictor.py`

Builds the **inverse-search front end** for inductors using k-nearest-neighbor search in specification space. It is designed to work together with the EM surrogate model.

The basic flow is:

1. Use kNN on specification space to retrieve candidate geometries.
2. Re-score those candidates with the EM surrogate.
3. Save the kNN model and associated geometry training set for later reuse.

It also includes utilities for evaluation plots and CSV export.

**Primary role**

- Support module for inductor inverse design.
- Used by `optimize_inductor.py`.

**Generated artifact**

- `DEV/MODELS/knn_model.pkl`

**Typical use cases**

- Train the inverse-search helper once and reuse it later.
- Retrieve geometry candidates close to a target specification vector.
- Evaluate inverse-prediction quality over a held-out test set.

**Programmatic usage**

```python
from PRIMITIVE_OPTIMIZERS import knn_with_emx_estimator_geom_predictor as knn_mod

knn_model, geom_train = knn_mod.train_knn_model(dataset_path)
```

**Note**

This file defines a `main()` function but does not currently enable it through an active `if __name__ == "__main__":` block in the repository version.

---

## `optimize_capacitor.py`

Fits a **polynomial regression model** for MIM capacitor behavior and uses it for both:

- direct capacitance prediction from `(Length, Width)`
- inverse search for candidate `(Length, Width)` pairs that meet a target capacitance

The script also supports equation export and stores the fitted polynomial model as a `.pkl` file for fast reuse.

**Primary role**

- User-facing capacitor optimizer.

**Default data/model paths**

- Dataset: `DEV/DATASETS/mimcap_dataset.csv`
- Model: `DEV/MODELS/mimcap_poly_model.pkl`

**Typical use cases**

- Train a compact polynomial surrogate for capacitor sizing.
- Predict capacitance for a proposed rectangle.
- Find feasible capacitor dimensions for a target capacitance under aspect-ratio and size constraints.

**Typical command**

```bash
python optimize_capacitor.py
```

**Example command**

```bash
python optimize_capacitor.py \
  --csv_path "$PROJECT_HOME/DEV/DATASETS/mimcap_dataset.csv" \
  --degree 2 \
  --predict_length 100 \
  --predict_width 22.9 \
  --target_cap 505 \
  --export_equation
```

---

## `optimize_inductor.py`

This is the main **inductor inverse-optimization driver** in the directory.

It combines:

- the forward EM surrogate from `emx_estimator.py`
- the inverse candidate-retrieval flow from `knn_with_emx_estimator_geom_predictor.py`

The optimizer supports both:

- **exact-style matching**, when all four target specs are given
- **partial matching**, where fixed specs are matched and unspecified specs are allowed to float

It also supports **variant-aware optimization** over turn patterns such as:

- `x.25`
- `x.5`
- `x.75`
- `x.1`

and can reject poor matches based on a maximum allowed relative error.

**Primary role**

- User-facing inductor optimizer.

**Default dataset path**

- `DEV/DATASETS/spiral_ind_data.csv`

**Typical use cases**

- Optimize for inductance only.
- Optimize for inductance plus one or more secondary EM specs.
- Search across multiple turn-pattern variants and keep only the acceptable result(s).

**Typical command**

```bash
python optimize_inductor.py
```

**Example commands**

Partial target:

```bash
python optimize_inductor.py --inductance 1044 --peak_q 10
```

Full target:

```bash
python optimize_inductor.py \
  --inductance 190 \
  --peak_q 28 \
  --peak_q_freq 40 \
  --srf 110
```

Single-variant search:

```bash
python optimize_inductor.py --single_variant
```

---

## `optimize_resistor.py`

Provides a simple **analytical resistor sizing sweep** based on sheet resistance:

```text
R = Rsheet × (L / W)
```

Unlike the EM-driven or learned-model scripts, this optimizer does not require a dataset or trained model. It sweeps feasible `(W, L)` pairs over a user-defined grid and returns the top candidates closest to the target resistance.

**Primary role**

- User-facing resistor optimizer.

**Typical use cases**

- Generate practical resistor dimensions for a desired resistance.
- Explore the tradeoff between resistor width and length under layout bounds.

**Typical command**

```bash
python optimize_resistor.py
```

**Example command**

```bash
python optimize_resistor.py \
  --R_target 1000 \
  --W_min 2 \
  --W_max 10 \
  --L_min 0.8 \
  --L_max 100 \
  --n_W 300 \
  --n_L 300 \
  --k 5
```

---

## `optimize_tline.py`

Uses **k-nearest-neighbor search** to propose transmission-line dimensions from a target inductance. Instead of averaging neighbors, the script selects the neighbor with the **minimum line length** among the retrieved candidates.

It can also generate an optional **interactive t-SNE visualization** in HTML format for dataset exploration and debugging.

**Primary role**

- User-facing T-line optimizer.

**Default dataset path**

- `DEV/DATASETS/tline_data.csv`

**Typical use cases**

- Predict `(Length, Width)` from an inductance target.
- Inspect the local neighborhood of candidate solutions in an interactive plot.

**Typical command**

```bash
python optimize_tline.py
```

**Example command**

```bash
python optimize_tline.py \
  --csv_path "$PROJECT_HOME/DEV/DATASETS/tline_data.csv" \
  --query_point 120 \
  --n_neighbors 5 \
  --make_plot
```

---

## Recommended Workflow

A practical way to use this directory is:

1. **Train or load reusable surrogate models**
   - `emx_estimator.py`
   - `knn_with_emx_estimator_geom_predictor.py`

2. **Run the user-facing primitive optimizers**
   - `optimize_capacitor.py`
   - `optimize_inductor.py`
   - `optimize_resistor.py`
   - `optimize_tline.py`

3. **Feed the selected geometry into the primitive generators/layout flow**
   - capacitor dimensions -> capacitor generator
   - inductor geometry -> inductor generator
   - resistor dimensions -> resistor generator
   - t-line dimensions -> line generator

---

## Model and Dataset Notes

Several scripts in this directory rely on datasets and serialized model files located under the repository `DEV` area. In the default configuration, these scripts expect the following structure:

```text
$PROJECT_HOME/
`-- DEV/
    |-- DATASETS/
    |   |-- mimcap_dataset.csv
    |   |-- spiral_ind_data.csv
    |   `-- tline_data.csv
    `-- MODELS/
        |-- emx_rf_model.pkl
        |-- knn_model.pkl
        `-- mimcap_poly_model.pkl
```

If these paths differ in a local setup, pass the dataset or model path explicitly using the available command-line arguments.

---

## Summary

`PRIMITIVE_OPTIMIZERS` provides the primitive-level intelligence layer for COmPOSER. Analytical sizing is used where a closed-form relation is sufficient, and surrogate-model-based optimization is used where EM behavior or inverse search is more complex. Together, these utilities help bridge the gap between target electrical specifications and layout-ready primitive dimensions.


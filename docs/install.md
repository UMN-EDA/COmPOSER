---
layout: default
title: Installation
permalink: /install/
eyebrow: Setup
description: Environment and dependency requirements for COmPOSER.
---

# Installation

COmPOSER has three environment layers:

1. Python packages for sizing, parsing, geometry generation, plotting, and GDS handling.
2. A working Gurobi installation for placement.
3. A compiled `hanan_router` binary for detailed routing.

## Recommended Setup

```bash
git clone <your-fork-or-clone-url>
cd COmPOSER
python3 -m venv .venv
source .venv/bin/activate
export PROJECT_HOME="$(pwd)"
```

## Python Dependencies

The repo `requirements.txt` lists these package families:

- `gdspy`
- `gurobipy`
- `imageio`
- `joblib`
- `matplotlib`
- `networkx`
- `numpy`
- `pandas`
- `plotly`
- `scikit_learn`
- `scipy`
- `Shapely`
- `tqdm`

### Important note about `requirements.txt`

The file currently contains duplicate pins for some packages, including `matplotlib`, `networkx`, `numpy`, and `pandas`. Treat it as a dependency inventory, not a guaranteed conflict-free lockfile.

For a clean environment, install a compatible set of versions used by your lab or project baseline, then validate the example flows.

## Gurobi

`perform_placement.py` imports `gurobipy`, so placement requires:

- Gurobi installed on your machine
- a valid license
- the Python package available in the same environment you use to run the flow

If Gurobi is missing, stage 3 placement will fail even if the earlier stages complete.

## Router Build

The detailed router lives in `ROUTER/hanan_router`.

Build it with:

```bash
cd ROUTER/hanan_router
make -j4
cd ../..
```

The expected binary path in the example configs is:

```text
ROUTER/hanan_router/hanan_router
```

## Mock PDK and Placeholder Assets

The repository already includes:

- `PDK/mock_65nm/layers.json`
- `FIXED_PRIMITIVES/pad.gds`
- `FIXED_PRIMITIVES/bga.gds`
- `FIXED_PRIMITIVES/nmos_bias_1.gds`
- `FIXED_PRIMITIVES/auto_gen_decap_lna_0_1.gds`

These are suitable for demonstrating the pipeline. For a real technology flow, replace them with technology-correct files while preserving the interfaces the scripts expect.

## Jekyll and GitHub Pages

This documentation site is stored entirely inside `docs/` and is compatible with GitHub Pages' standard Jekyll workflow. No custom plugins are required.

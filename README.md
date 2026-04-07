# COmPOSER

COmPOSER is an RF/mm-wave design automation framework for generating layout-aware implementations of circuits such as low-noise amplifiers (LNAs) and power amplifiers (PAs). It connects high-level design targets to circuit sizing, primitive generation, placement, routing, and final layout construction in one flow.

Instead of treating circuit design and physical layout as completely separate steps, COmPOSER brings layout considerations in early. The framework uses equation-based sizing, learned or surrogate passive models, parameterized primitive generators, a placement engine, a detailed router, and power-grid generation to produce layouts that are physically meaningful and easier to validate.

COmPOSER can be used in two ways:

- as a full end-to-end flow for RF layout synthesis
- as a modular toolkit where users run only the sizers, primitive generators, placer, router, or utility scripts they need

## Documentation Website

Project documentation is available at:

[https://umn-eda.github.io/COmPOSER/](https://umn-eda.github.io/COmPOSER/)

The website source is stored in [`docs/`](docs/).

## Repository Structure

- `EXAMPLES/`: Example LNA and PA designs, configurations, and generated outputs
- `DATASETS/`: Reference-format datasets for passive optimization
- `MODELS/`: Location for trained `.pkl` models used by the flow
- `PRIMITIVE_GENERATORS/`: Standalone layout generators for inductors, capacitors, resistors, T-lines, CPWDs, and device blocks
- `PRIMITIVE_OPTIMIZERS/`: Geometry-selection and surrogate-model scripts for passive elements
- `ROUTER/`: Hanan-grid detail router
- `PDK/`: Mock PDK layer description used by the public flow
- `FIXED_PRIMITIVES/`: Black-box or fixed primitive GDS cells
- `utils/`: Helper scripts for LEF generation, GDS assembly, and related tasks

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/UMN-EDA/COmPOSER.git
cd COmPOSER
```

### 2. Create a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Note:

- `requirements.txt` should be treated as the dependency list used by the repo.
- Some environments may require you to resolve package-version conflicts manually.

### 4. Set the project root

Some scripts expect `PROJECT_HOME` to point to the repository root:

```bash
export PROJECT_HOME="$(pwd)"
```

### 5. Build the router

```bash
cd ROUTER/hanan_router
make -j4
cd ../..
```

This creates the router binary expected by the example configs:

```text
ROUTER/hanan_router/hanan_router
```

### 6. Make sure Gurobi is available

Placement uses `gurobipy`, so you need:

- a working Gurobi installation
- a valid license
- the Python package visible inside your environment

## High-Level Usage

The main shell driver is:

```bash
./composer.sh
```

You can run the full flow on an example config like this:

```bash
./composer.sh EXAMPLES/LNA_1/config.json
```

or:

```bash
./composer.sh EXAMPLES/PA_1/config.json
```

You can also start from a later step:

```bash
./composer.sh EXAMPLES/LNA_1/config.json placement
```

or run only one step:

```bash
./composer.sh EXAMPLES/LNA_1/config.json only routing
```

## Flow Overview

At a high level, COmPOSER performs:

1. Initial sizing
   Converts target circuit specs into initial device and passive values.
2. Netlist parsing and primitive generation
   Generates layout-ready primitive blocks and exports design JSON for physical synthesis.
3. Placement
   Places the generated blocks using constraints and RF-critical net weighting.
4. Routing and LEF/GDS generation
   Builds routing inputs, runs detailed routing, and assembles the routed GDS.
5. PDN generation
   Adds the power grid and produces the final layout output.

## Main Entry Points

- `perform_initial_sizing.py`
- `parse_netlist.py`
- `perform_placement.py`
- `generate_routing_inputs.py`
- `perform_routing.py`
- `composer.sh`

These can all be run independently if you want to use only part of the framework.

## Important Notes

- The datasets in `DATASETS/` are reference datasets for schema and unit compatibility. Users should generate their own datasets for real technologies.
- The models in `MODELS/` are not committed and are expected to be created locally.
- The mock PDK and fixed primitives are intended for public-flow validation and prototyping, not as production tapeout collateral.

## License

This repository is distributed under the license in [`LICENSE`](LICENSE).

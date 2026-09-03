[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE) [![docs](https://img.shields.io/badge/docs-passing-brightgreen.svg)](https://umn-eda.github.io/COmPOSER/)

# COmPOSER: Circuit Optimization of mm-wave/RF circuits with Performance-Oriented Synthesis for Efficient Realizations

COmPOSER is an open-source RF/mm-wave design automation framework for end-to-end design of circuits such as low-noise amplifiers (LNAs) and power amplifiers (PAs). It connects high-level design targets to circuit sizing, primitive generation, placement, routing, and final layout construction in one integrated flow.

Instead of treating circuit design and physical layout as completely separate steps, COmPOSER brings layout awareness in early. The framework combines equation-based sizing, learned or surrogate passive models, parameterized primitive generators, a placement engine, a detailed router, and power-grid generation to produce layouts that are physically meaningful and easier to validate.

Paper: [COmPOSER on arXiv](https://arxiv.org/abs/2603.20486)

## Two Ways to Use COmPOSER

### End-to-End RF Layout Synthesis

Use COmPOSER as a complete automation flow when you want to start from user specifications and a circuit netlist, then generate sized designs, layout-ready primitives, placement, routing, and final physical layout outputs.

### Modular RF Design Toolkit

Use COmPOSER as a reusable toolkit when you only need one part of the framework, such as the stage 1 sizers, primitive generators, primitive optimizers, placement engine, router, or layout-conversion utilities.

## Documentation

For the full user guide, examples, and flow reference, visit the **[COmPOSER Documentation Website](https://umn-eda.github.io/COmPOSER/)**.

The website source is stored in [`docs/`](docs/).

## Repository Structure

| Path | Description |
| --- | --- |
| `EXAMPLES/` | Example LNA and PA designs, configuration files, and representative generated outputs |
| `DATASETS/` | Reference-format datasets for passive optimization and model fitting |
| `MODELS/` | Location for trained `.pkl` models used by the flow |
| `PRIMITIVE_GENERATORS/` | Standalone layout generators for inductors, capacitors, resistors, T-lines, CPWDs, and device blocks |
| `PRIMITIVE_OPTIMIZERS/` | Geometry-selection and surrogate-model scripts for passive elements |
| `ROUTER/` | Hanan-grid detailed router and related routing infrastructure |
| `PDK/` | Mock PDK layer description used by the public flow |
| `FIXED_PRIMITIVES/` | Black-box or fixed primitive GDS cells |
| `utils/` | Helper scripts for LEF generation, GDS assembly, and related utilities |
| `composer.sh` | Main shell driver for the end-to-end flow |

### Main Scripts

| Script | Description |
| --- | --- |
| `perform_initial_sizing.py` | Runs stage 1 sizing and maps the selected design values into the sized netlist |
| `lna_stage_1_sizer.py` | Equation-based stage 1 sizing engine for LNA designs |
| `pa_stage_1_sizer.py` | Equation-based stage 1 sizing engine for PA designs |
| `map_initial_size_to_netlist.py` | Maps stage 1 sizing outputs back into the SPICE netlist |
| `parse_netlist.py` | Parses the sized netlist, selects or generates primitive layouts, and exports stage 2 design JSON |
| `perform_placement.py` | Runs the placement engine and generates placement JSON and placement GDS |
| `generate_routing_inputs.py` | Converts primitive GDS files into LEF files for routing |
| `perform_routing.py` | Runs detailed routing, routed GDS generation, and PDN generation |

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/UMN-EDA/COmPOSER.git
cd COmPOSER
```

Python 3.10 or newer is recommended.

### 2. Create and activate a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade "pip<25.1"
python -m pip install -r requirements.txt
```

Notes:

- `requirements.txt` should be treated as the dependency list used by the repository.
- The `-r` option is required. Without it, pip searches for a package literally named `requirements.txt`.
- The pinned dependency set is validated with CPython 3.8 on Linux x86-64.

### 4. Set the required environment variables

COmPOSER expects the project root to be defined, and placement requires a valid Gurobi license file. `PROJECT_HOME` must point directly to the checkout containing `composer.sh`; do not append `DEV` or another directory name.

Using `csh`/`tcsh` style:

```csh
setenv PROJECT_HOME /absolute/path/to/COmPOSER
setenv GRB_LICENSE_FILE ~/gurobi.lic
```

If you are using `bash` or `zsh`, the equivalent is:

```bash
export PROJECT_HOME=/absolute/path/to/COmPOSER
export GRB_LICENSE_FILE=~/gurobi.lic
```

You should replace `~/RF_DESIGN_AUTOMATION` with the actual path to your local COmPOSER checkout if needed.

### 5. Build the router

```bash
g++ --version
make -C ROUTER/hanan_router clean
make -C ROUTER/hanan_router -j4
```

Run `clean` and `make` as separate commands. The original router Makefile has no explicit `all` target. Always rebuild locally on a new machine instead of reusing a committed or copied binary. This creates the router binary expected by the example configurations:

```text
ROUTER/hanan_router/hanan_router
```

Build the optional dedicated power-grid router used by the connected-PDN LNA
example:

```bash
make -C ROUTER/pdn_router
```

#### Compiler and runtime errors

The error `g++: error: unrecognized command line option -std=c++14` means the selected compiler is too old. GCC 4.8.5 is a common source of this error. The router requires C++14; GCC 7 or newer is recommended. On a module-based system, locate and load an available newer compiler, verify it, and rebuild both routers:

```bash
module avail gcc
module load gcc/9       # use a version available on your system
g++ --version
make -C ROUTER/hanan_router clean
make -C ROUTER/hanan_router -j4
make -C ROUTER/pdn_router clean
make -C ROUTER/pdn_router -j4
```

The error `GLIBCXX_3.4.21 not found` means the router binary was compiled against a newer `libstdc++` than the runtime currently being loaded. Do not copy router binaries between machines. Load the compiler/runtime intended for the current machine, run `make clean`, and rebuild locally. Inspect the library selected at runtime with:

```bash
ldd ROUTER/hanan_router/hanan_router | grep libstdc++
```

On CentOS/RHEL 7 with a site-provided Software Collection, a newer compiler may be enabled before rebuilding:

```bash
source /opt/rh/devtoolset-11/enable
g++ --version
```

On a cluster, use the GCC module name provided by that site. Do not remove `-std=c++14` from the Makefile as a workaround.

### 6. Make sure Gurobi is available

Placement uses `gurobipy`, so you need:

- a working Gurobi installation
- your own valid Gurobi license
- the `GRB_LICENSE_FILE` environment variable set correctly
- the Python package visible inside your environment

## High-Level Usage

The main shell driver is:

```bash
./composer.sh
```

Run the full flow on an example config:

```bash
./composer.sh EXAMPLES/LNA_1/config.json
```

or:

```bash
./composer.sh EXAMPLES/PA_1/config.json
```

Start from a later step:

```bash
./composer.sh EXAMPLES/LNA_1/config.json placement
```

Run only one step:

```bash
./composer.sh EXAMPLES/LNA_1/config.json only routing
```

Run the isolated LNA routing flow that connects pads, internal power pins, and
generated decaps to their nearest PDN rails:

```bash
python3 perform_routing_with_pdn.py --config EXAMPLES/LNA_1/config_pdn.json
```

This flow leaves the normal router and `perform_routing.py` behavior unchanged.
It generates an augmented placement and LEF under `lna_1/stage_3/pdn/`, routes
only the configured VDD and GND nets with `pdn_router`, and writes a hierarchical
final GDS. The final hierarchy contains `PDN_ROUTES` with one `PDN_NET_*` child
per routed power net. Adjust `pdn_routing.decap_count` in `config_pdn.json` to
control the number of generated decaps used by the example.

## Flow Overview

At a high level, COmPOSER performs:

1. Initial sizing  
   Converts target circuit specifications into initial device and passive values.
2. Netlist parsing and primitive generation  
   Generates layout-ready primitive blocks and exports design JSON for physical synthesis.
3. Placement  
   Places the generated blocks using user constraints and RF-critical net weighting.
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

## Citation

COmPOSER has been accepted for publication in the Proceedings of the ACM/IEEE Design Automation Conference (DAC) 2026. If you use COmPOSER in your research, please cite our work:

```bibtex
@article{ghosh2026composer,
  title={COmPOSER: Circuit Optimization of mm-wave/RF circuits with Performance-Oriented Synthesis for Efficient Realizations},
  author={Ghosh, Subhadip and Peri, Surya Srikar and Ramprasath, S. and Berhan, Sosina A. and Gebru, Endalk Y. and Harjani, Ramesh and Sapatnekar, Sachin S.},
  journal={arXiv preprint arXiv:2603.20486},
  year={2026}
}
```

Paper link: [https://arxiv.org/abs/2603.20486](https://arxiv.org/abs/2603.20486)

## Contact

For any questions, please contact:

**Subhadip Ghosh**  
University of Minnesota  
ghosh211@umn.edu

## License

This repository is distributed under the license in [`LICENSE`](LICENSE).

---
layout: default
title: Paper Overview
permalink: /paper/
eyebrow: Paper
description: Paper-aligned overview of COmPOSER based on the attached arXiv manuscript.
---

# Paper Overview

This documentation site is aligned to the paper:

**COmPOSER: Circuit Optimization of mm-wave/RF circuits with Performance-Oriented Synthesis for Efficient Realizations**

Authors listed in the attached PDF:

- Subhadip Ghosh
- Surya Srikar Peri
- Ramprasath S.
- Sosina A. Berhan
- Endalk Y. Gebru
- Ramesh Harjani
- Sachin S. Sapatnekar

Paper metadata visible in the attached PDF:

- arXiv: `2603.20486v2`
- DOI: `10.48550/arXiv.2603.20486`
- PDF date: April 3, 2026

## Paper Framing

The paper presents COmPOSER as an **open-source end-to-end RF/mm-wave design automation framework** that translates user target specifications into optimized circuits with layouts.

The paper-level description emphasizes that COmPOSER unifies:

- schematic synthesis
- layout generation for active and passive devices
- placement and routing
- physics-based equations
- machine-learning-driven electromagnetic models

## Paper-Aligned Stage Names

The website now follows the paper's conceptual decomposition:

### Stage 1: Hybrid analytical sizing

This stage turns target specs into active and passive sizes using analytical equations plus ML/EM-informed passive estimation.

In the public repo, this corresponds mainly to:

- `perform_initial_sizing.py`
- `lna_stage_1_sizer.py`
- `pa_stage_1_sizer.py`
- `map_initial_size_to_netlist.py`

### Stage 2: Primitive block layout generator

This stage translates sized circuit elements into DRC-clean primitive layouts for actives, passives, and matching structures.

In the public repo, this corresponds mainly to:

- `parse_netlist.py`
- `PRIMITIVE_GENERATORS/`
- `PRIMITIVE_OPTIMIZERS/`

### Stage 3: Layout synthesis

The paper describes this stage as hierarchical placement, routing, and PDN construction with user constraints such as critical nets, halo spacing, and PDN density.

In the public repo, this corresponds mainly to:

- `perform_placement.py`
- `generate_routing_inputs.py`
- `perform_routing.py`
- `perform_power_grid_multi_level.py`
- `ROUTER/hanan_router`

### Stage 4: Post-layout verification

The paper describes a final verification stage using EM and SPICE validation, with re-synthesis if constraints are not met.

This stage is part of the paper's evaluation flow. The public repo already reflects the synthesis side of that workflow, but the full commercial verification environment described in the paper is broader than what is bundled directly in this repository.

## Important Public-Repo vs Paper Distinction

The paper reports results using a commercial 65 nm process flow and post-layout verification infrastructure, including Cadence EMX and Spectre.

This public repository includes:

- the open-source flow structure
- mock and placeholder assets for datasets, fixed primitives, and PDK layers
- the layout-generation, placement, routing, and PDN logic

So the website now aligns its terminology and architecture with the paper, while still being careful not to imply that every commercial validation dependency from the paper is shipped inside this repo.

## Validation Story from the Paper

The extracted PDF text indicates that the paper evaluates:

- four LNAs
- three PAs
- post-layout behavior
- Smith-chart-based matching quality
- stability
- runtime and productivity gains

That is why the site now emphasizes:

- layout awareness
- user-specified RF-critical nets
- per-net weighting
- passive geometry selection
- placement and routing as first-class parts of the method, not post-processing

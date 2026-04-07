---
layout: default
title: Configuration
permalink: /configuration/
eyebrow: Reference
description: Reference for the main COmPOSER config.json interface.
---

# Configuration

The main `config.json` is the primary interface between the user and the full flow. Every major stage reads from it either directly or indirectly.

The most representative reference files in this repo are:

- `EXAMPLES/LNA_1/config.json`
- `EXAMPLES/PA_1/config.json`

## Top-Level Structure

```json
{
  "datasets": { "...": "..." },
  "project_name": "lna_1",
  "stage_1_config": "EXAMPLES/LNA_1/lna_stage_1_config.json",
  "stage_1_sizer": "lna_stage_1_sizer.py",
  "stage_1_mapping_script": "map_initial_size_to_netlist.py",
  "stage_1_map_file": "EXAMPLES/LNA_1/stage_1_map.json",
  "design_requirements": { "...": "..." },
  "design": { "...": "..." },
  "scale": 1000,
  "pdk": "PDK/mock_65nm/layers.json",
  "topcell": "lna",
  "decaps": { "...": "..." },
  "pad_direction": ["W", "N"],
  "pad_mode": "periphery",
  "placement": { "...": "..." },
  "routing": { "...": "..." },
  "pdn": { "...": "..." }
}
```

## Top-Level Keys

| Key | Meaning |
| --- | --- |
| `datasets` | Paths to the CSV datasets used by primitive optimizers and model setup. |
| `project_name` | Output run directory created by the scripts. |
| `stage_1_config` | Path to the design-specific stage 1 sizing constants. |
| `stage_1_sizer` | Stage 1 sizing entry point, for example `lna_stage_1_sizer.py` or `pa_stage_1_sizer.py`. |
| `stage_1_mapping_script` | Script that maps stage 1 results back into the netlist. |
| `stage_1_map_file` | JSON describing how stage 1 output keys map onto netlist instance annotations. |
| `design_requirements` | Electrical targets such as frequency, gain, NF, bandwidth, or PA saturation target. |
| `design` | The design file paths: unsized netlist, sized netlist, and net weights JSON. |
| `scale` | Integer geometry scaling factor used throughout layout and JSON export. Example files use `1000`. |
| `pdk` | Path to `layers.json`. |
| `topcell` | Top subcircuit or design name used in generated files such as `lna_design.json` or `pa_placement.gds`. |
| `decaps` | Controls automatic decap insertion during parsing. |
| `pad_direction` | Allowed IO directions used by placement and PDN logic. |
| `pad_mode` | IO style. The code supports `periphery` and `bga`. |
| `placement` | Placement constraints file and solver settings. |
| `routing` | Router binary path and router constraint JSON path. |
| `pdn` | PDN stripe width and gap values. |

## `datasets`

Typical keys seen in the examples:

- `spiral_inductor`
- `tline`
- `mimcap`
- `small_mimcap`
- `cpwd`

These dataset files are schema references. Users should regenerate them for their own process while keeping the same columns and units.

## `design_requirements`

The examples expose both LNA- and PA-relevant fields:

- `freq_ghz`
- `nf_req_db`
- `gain_req_db`
- `bw_req_ghz`
- `s11_req_db`
- `pwr_req_mw`
- `p_sat_db`

Not every field is used equally by every stage 1 sizer, but keeping them together makes it easier to reuse one high-level config format across design classes.

## `design`

| Key | Meaning |
| --- | --- |
| `input_unsized_netlist` | The initial netlist the user provides. |
| `input_netlist` | The sized netlist generated after stage 1 mapping. |
| `net_weights` | JSON with net priorities for placement and routing. |

## `decaps`

| Key | Meaning |
| --- | --- |
| `add_decaps` | Whether automatic decaps are appended during parsing. |
| `decap_val` | Value assigned to each inserted decap. |
| `num_decaps` | Number of decaps to insert. |

## `placement`

| Key | Meaning |
| --- | --- |
| `placement_constraints` | Constraint JSON path. |
| `timelimit` | Gurobi solve time limit. |
| `aspect_ratio` | Target aspect ratio. `0` means unconstrained. |
| `level` | Placement formulation mode used internally by the script. |
| `weight_hpwl` | Weighting for HPWL in the objective. |
| `plot_html` | Enables interactive HTML plotting when set to `true`. |

## `routing`

| Key | Meaning |
| --- | --- |
| `router_bin` | Path to the compiled `hanan_router` binary. |
| `routing_constraints` | Path to the non-default rule JSON consumed by the router. |

## `pdn`

| Key | Meaning |
| --- | --- |
| `pdn_width` | Width of PDN polygons. |
| `pdn_gap` | Gap used to derive PDN pitch. |

## Configuration Advice

- Use the example configs as templates rather than the root-level placeholder `config.json`.
- Keep paths repo-relative when possible.
- Keep `project_name` unique per run if you want to preserve old outputs.
- Keep `topcell` aligned with the top subcircuit name in the SPICE input.
- If you replace the mock PDK, keep the `layers.json` structure compatible with the scripts.

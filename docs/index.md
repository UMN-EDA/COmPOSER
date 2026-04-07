---
layout: default
title: COmPOSER Documentation
permalink: /
eyebrow: Documentation
description: Documentation for the COmPOSER RF design automation framework.
---

# COmPOSER

COmPOSER is an RF design automation framework that connects equation-based stage 1 sizing, primitive generation, placement, detail routing, and power-grid generation into one reproducible flow.

The repository is organized so that you can use the full pipeline or only the pieces you need. You can run the end-to-end shell driver, or you can call the sizers, parser, placement engine, router, primitive generators, and utilities independently in your own project.

<div class="hero-grid">
  <div class="callout">
    <h3>What this site covers</h3>
    <p>These pages were written from the actual repository structure, example configurations, datasets, and entry-point scripts in this repo.</p>
    <p>They focus on the user-facing inputs: <code>config.json</code>, example directories, datasets, primitive assets, standalone commands, and generated outputs.</p>
  </div>
  <div class="callout">
    <img src="{{ '/assets/img/flow-overview.svg' | relative_url }}" alt="COmPOSER flow overview">
  </div>
</div>

## Main Ideas

<div class="card-grid">
  <div class="mini-card">
    <h3>Stage 1</h3>
    <p>Equation-based LNA or PA sizing produces an initial best design JSON and maps those values into a sized netlist.</p>
  </div>
  <div class="mini-card">
    <h3>Stage 2</h3>
    <p>The sized netlist is parsed into primitive GDS blocks, connectivity, pad information, and machine-readable design JSON.</p>
  </div>
  <div class="mini-card">
    <h3>Stage 3</h3>
    <p>Placement, LEF generation, detail routing, final routed GDS assembly, and PDN generation complete the layout flow.</p>
  </div>
  <div class="mini-card">
    <h3>Standalone Use</h3>
    <p>Primitive generators, optimizers, the Hanan router, and conversion utilities can all be reused outside the full flow.</p>
  </div>
</div>

## Start Here

- Read [Installation]({{ '/install/' | relative_url }}) for environment requirements, router build notes, and Python setup.
- Read [Quickstart]({{ '/quickstart/' | relative_url }}) to run one of the included LNA or PA examples.
- Read [Configuration]({{ '/configuration/' | relative_url }}) for the complete meaning of the main `config.json`.
- Read [Examples]({{ '/examples/' | relative_url }}) for the file-by-file meaning of `LNA_1` to `LNA_4` and `PA_1` to `PA_3`.

## Important Notes

> The CSV files in `DATASETS/` are reference-format datasets, not production datasets. Users should generate their own datasets with the same column names and the same units expected by the scripts.

> The `MODELS/` directory is intended to hold trained `.pkl` artifacts, but those model files are not committed. They are created locally during training or setup.

> The mock PDK and fixed primitive GDS files are flow-compatible placeholders. They are useful for validating the pipeline, but users should substitute technology-correct assets for real deployment.

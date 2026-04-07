---
layout: default
title: Hanan Router
permalink: /hanan-router/
eyebrow: Router
description: Reference page for the Hanan-grid A-star router used by COmPOSER.
---

# Hanan Router

COmPOSER uses the router in `ROUTER/hanan_router`, a rectilinear detail router based on a modified A-star search over a Hanan grid.

## What It Supports

According to the bundled router README, the router honors:

- Manhattan spacing between metal and via shapes
- metal widths per layer
- single-cut and multi-cut vias
- user-specified non-default rules at block or net level
- per-net or per-block overrides for spacing, widths, allowed layers, and obstacles

## Build

```bash
cd ROUTER/hanan_router
make -j4
```

The build requires:

- a C++14-capable compiler or newer
- `make`

The expected output is the binary:

```text
ROUTER/hanan_router/hanan_router
```

## Router CLI

From the bundled README, the router interface is:

```text
hanan_router
  -d <layers.json>
  -p <placement file>
  -l <lef file>
  -s <lef scaling>
  -uu <user units scaling>
  -ndr <constraints.json>
  -o <output dir>
```

`perform_routing.py` additionally passes:

- `-t <topcell>`
- `-log <route.log>`

## Inputs Used by COmPOSER

In the COmPOSER flow, the router receives:

- the mock or real PDK `layers.json`
- the placement JSON exported by the placer
- the merged primitive LEF file
- the router constraint JSON from the main config

## Outputs Used by COmPOSER

The router writes:

- DEF
- interim hierarchical LEF
- detailed router log

COmPOSER then converts those into the routed GDS using `utils/gen_rt_hier_gds.py`.

## Why This Page Matters

You can use the Hanan router separately from the rest of COmPOSER if you already have:

- a compatible placement JSON
- compatible LEF macros
- a compatible `layers.json`

That makes it a reusable standalone router, not just a hidden internal dependency.

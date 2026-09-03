#!/usr/bin/env python3
import argparse
import json
import re

import gdspy


def load_layer_map(path):
    with open(path, "r") as f:
        data = json.load(f)
    return {
        entry["Layer"]: (
            int(entry["GdsLayerNo"]),
            int(entry.get("GdsDatatype", {}).get("Draw", 0))
        )
        for entry in data["Abstraction"]
        if "GdsLayerNo" in entry
    }


def add_def_routes(lib, top_cell, def_file, layer_map, scale):
    rect_re = re.compile(
        r"\+\s+RECT\s+(\S+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+"
        r"\(\s*(-?\d+)\s+(-?\d+)\s*\)"
    )
    in_nets = False
    current_net = None
    route_cells = {}
    route_group = lib.new_cell("PDN_ROUTES")
    with open(def_file, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("NETS "):
                in_nets = True
                continue
            if stripped == "END NETS":
                break
            if not in_nets:
                continue
            if stripped.startswith("- "):
                current_net = stripped.split()[1]
            match = rect_re.search(stripped)
            if not match or not current_net:
                continue
            layer_name = match.group(1)
            if layer_name not in layer_map:
                continue
            x0, y0, x1, y1 = [int(match.group(i)) / scale for i in range(2, 6)]
            layer, datatype = layer_map[layer_name]
            if current_net not in route_cells:
                cell_name = "PDN_NET_" + re.sub(r"[^A-Za-z0-9_$?]", "_", current_net)
                route_cells[current_net] = lib.new_cell(cell_name)
            route_cells[current_net].add(gdspy.Rectangle(
                (min(x0, x1), min(y0, y1)),
                (max(x0, x1), max(y0, y1)),
                layer=layer,
                datatype=datatype
            ))
    for route_cell in route_cells.values():
        route_group.add(gdspy.CellReference(route_cell))
    top_cell.add(gdspy.CellReference(route_group))


def main():
    parser = argparse.ArgumentParser(description="Overlay dedicated PDN router DEF onto a PDN GDS")
    parser.add_argument("--config", required=True)
    parser.add_argument("--infile", required=True)
    parser.add_argument("--deff", required=True)
    parser.add_argument("--top", required=True)
    parser.add_argument("--outfile", required=True)
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg = json.load(f)
    layer_map = load_layer_map(cfg["pdk"])

    lib = gdspy.GdsLibrary()
    lib.read_gds(args.infile)
    if args.top not in lib.cells:
        raise ValueError(f"Base design cell not found: {args.top}")
    top_cells = lib.top_level()
    if len(top_cells) != 1:
        raise ValueError(f"Expected one final top cell, found {[cell.name for cell in top_cells]}")
    add_def_routes(lib, top_cells[0], args.deff, layer_map, cfg["scale"])
    lib.write_gds(args.outfile)
    print(f"Saved connected PDN GDS: {args.outfile}")


if __name__ == "__main__":
    main()

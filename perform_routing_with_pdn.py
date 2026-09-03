#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import json

def load_config(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
    return cfg

def run_step(step_name, cmd):
    print(f">>>>>>>>>>>> Running: {step_name}")
    print("Command:", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)
    print(f"Finished {step_name}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Python replacement for routing bash flow."
    )
    parser.add_argument("--config", default="config.json")

    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)
    router_binary = cfg["routing"]["router_bin"]
    pdk = cfg["pdk"]

    project_dir=cfg["project_name"]
    top_name = cfg["topcell"]
    placement_json = os.path.join(project_dir, "stage_3", "placement", f"{top_name}_placement.json")
    primitive_lef = os.path.join(project_dir, "stage_3", "routing", "lef", f"{top_name}_primitives.lef")
    router_out = os.path.join(project_dir, "stage_3", "routing")
    cmd1 = [
        router_binary,
        "-d", pdk,
        "-p", placement_json,
        "-t", top_name,
        "-l", primitive_lef,
        "-uu", str(1),
        "-s", str(1),
        "-o", router_out,
        "-ndr", cfg["routing"]["routing_constraints"],
        "-log", f"{router_out}/route.log"
    ]
    gds_rt_script = "utils/gen_rt_hier_gds.py"
    final_primitive_gds = os.path.join(project_dir, "stage_3", "placement", "primitives")
    cmd2 = [
        sys.executable,
        gds_rt_script,
        "-p", placement_json,
        "-g", final_primitive_gds,
        "-i", router_out,
        "-t", top_name,
        "-l", pdk,
        "-d", f"{router_out}/{top_name}.def",
        "--out", f"{router_out}/{top_name}.gds",
        "--net_gds_dir", router_out
    ]
    pdn_out = os.path.join(project_dir, "stage_3", "pdn")
    os.makedirs(pdn_out, exist_ok=True)
    pdn_script = "perform_power_grid_with_pdn_routing.py"
    pdn_grid_gds = os.path.join(pdn_out, f"{top_name}_grid.gds")
    pdn_constraints = os.path.join(pdn_out, f"{top_name}_router_constraints.json")
    pdn_placement = os.path.join(pdn_out, f"{top_name}_pdn_placement.json")
    pdn_lef = os.path.join(pdn_out, f"{top_name}_pdn_primitives.lef")
    pdn_route_out = os.path.join(pdn_out, "routing")
    os.makedirs(pdn_route_out, exist_ok=True)
    cmd3 = [
        sys.executable,
        pdn_script,
        "--config", args.config,
        "--infile", f"{router_out}/{top_name}.gds",
        "--top", top_name,
        "--outfile", pdn_grid_gds,
        "--io-direction", *cfg["pad_direction"],
        "--router-constraints", pdn_constraints,
        "--signal-def", f"{router_out}/{top_name}.def",
        "--placement-output", pdn_placement,
        "--lef-output", pdn_lef
    ]
    cmd4 = [
        cfg["pdn_routing"]["router_bin"],
        "-d", pdk,
        "-p", pdn_placement,
        "-t", top_name,
        "-l", pdn_lef,
        "-uu", str(1),
        "-s", str(1),
        "-o", pdn_route_out,
        "-ndr", pdn_constraints,
        "-log", os.path.join(pdn_route_out, "route.log")
    ]
    cmd5 = [
        sys.executable,
        "utils/gen_pdn_rt_gds.py",
        "--config", args.config,
        "--infile", pdn_grid_gds,
        "--deff", os.path.join(pdn_route_out, f"{top_name}.def"),
        "--top", top_name,
        "--outfile", os.path.join(pdn_out, f"{top_name}_final.gds")
    ]

    run_step("ROUTING", cmd1)
    run_step("GDS_GENERATION", cmd2)
    run_step("POWER_GRID_GENERATION", cmd3)
    run_step("POWER_GRID_ROUTING", cmd4)
    run_step("POWER_GRID_GDS", cmd5)

    print("All steps completed successfully.")


if __name__ == "__main__":
    main()

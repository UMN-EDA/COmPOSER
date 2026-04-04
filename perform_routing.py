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
        "--out", f"{router_out}/{top_name}.gds"
    ]
    pdn_out = os.path.join(project_dir, "stage_3", "pdn")
    os.makedirs(pdn_out, exist_ok=True)
    pdn_script = "perform_power_grid_multi_level.py"
    cmd3 = [
        sys.executable,
        pdn_script,
        "--infile", f"{router_out}/{top_name}.gds",
        "--top", top_name,
        "--outfile", f"{pdn_out}/{top_name}_final.gds",
        "--io-direction", *cfg["pad_direction"]
    ]

    run_step("ROUTING", cmd1)
    run_step("GDS_GENERATION", cmd2)
    run_step("POWER_GRID", cmd3)

    print("All steps completed successfully.")


if __name__ == "__main__":
    main()

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
    print(f"\n=== {step_name} ===")
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, check=True)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Python replacement for routing bash flow."
    )
    parser.add_argument("--config", default="config.json")

    return parser.parse_args()

def main():
    args = parse_args()
    cfg = load_config(args.config)
    stage_1_script = cfg["stage_1_sizer"]
    mapping_script = cfg["stage_1_mapping_script"]
    
    project_dir=cfg["project_name"]
    top_name = cfg["topcell"]
    os.makedirs(project_dir, exist_ok = True)
    stage_1_dir = os.path.join(project_dir, "stage_1")
    os.makedirs(stage_1_dir, exist_ok=True)
    
    cmd1 = [
        sys.executable,
        stage_1_script,
        "--config", args.config,
        "--out-json", os.path.join(stage_1_dir, f"best_{top_name}_design.json"),
        "--out-csv", os.path.join(stage_1_dir, f"all_{top_name}_designs.csv"),
    ]
    run_step("Running Stage 1 sizer", cmd1)

    cmd2 = [
        sys.executable, 
        mapping_script,
        "--netlist", cfg["design"]["input_unsized_netlist"], 
        "--design-json", os.path.join(stage_1_dir, f"best_{top_name}_design.json"),
        "--mapping-json", cfg["stage_1_map_file"],
        "--output", cfg["design"]["input_netlist"] 
    ]

    run_step("Mapping the sizes to netlist", cmd2)

    print("Sizing completed successfully.")

if __name__ == "__main__":
    print(f"Estimating initial sizes from specs")
    main()


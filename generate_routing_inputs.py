#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
import time
import json
from pathlib import Path
import os
from utils.convert_gds2lef import GDS2_LEF
from utils import combine_primitive_lefs


def load_config(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
    return cfg



def run_cmd(cmd):
    print("Running:", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def convert_all_gds_to_lef(primitives_dir, layer_json, outdir, scale, piniso=True):
    primitives_dir = Path(primitives_dir)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    gds_files = sorted(primitives_dir.glob("*.gds"))

    if not gds_files:
        print(f"[WARN] No GDS files found in {primitives_dir}")
        return 0

    for gdsfile in gds_files:
        cellname = gdsfile.stem
        print(f"Processing {gdsfile} -> {cellname}")

        gds2lef = GDS2_LEF(
            layerfile=layer_json,
            gdsfile=str(gdsfile),
            name=cellname
        )
        gds2lef.writeLEF(
            outdir=str(outdir) + "/",
            scale=scale,
            piniso=piniso
        )

    return len(gds_files)


def combine_lefs(outdir, delete_file):
    delete_file = Path(delete_file)
    if delete_file.exists():
        print(f"Deleting existing LEF file: {delete_file}")
        delete_file.unlink()
    combine_primitive_lefs.combine_lefs(input_dir = outdir, output_file = delete_file )

def parse_args():
    parser = argparse.ArgumentParser(
        description="Python replacement for the steps: clean LEF dir, convert GDS to LEF, combine LEFs."
    )

    parser.add_argument("--config", default="config.json", help="Input config.json with all user inputs")

    parser.add_argument(
        "--output-lef",
        default="primitives.lef",
        help='Final combined LEF filename. Default: primitives.lef'
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1000,
        help='Scale passed to convert_gds2lef.py. Default: 1000'
    )
    parser.add_argument(
        "--timelog",
        default="placer_time.log",
        help='Timing log file. Default: placer_time.log'
    )

    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)
    project_dir=cfg["project_name"]
    top_name = cfg["topcell"]
    stage_3_dir_place = os.path.join(project_dir, "stage_3", "placement", "primitives")
    stage_3_dir_route = os.path.join(project_dir, "stage_3", "routing")
    os.makedirs(stage_3_dir_route, exist_ok=True)
    lef_dir = os.path.join(stage_3_dir_route, "lef")
    print(f"Preparing LEF directory: {lef_dir}")
    if os.path.exists(lef_dir):
        for item in os.listdir(lef_dir):
            item_path = os.path.join(lef_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
    else:
        os.makedirs(lef_dir, exist_ok=True)

    print("Converting all GDS -> LEF...")
    nfiles = convert_all_gds_to_lef(
        primitives_dir=stage_3_dir_place,
        layer_json=cfg["pdk"],
        outdir=lef_dir,
        scale=cfg["scale"],
        piniso=True
    )
    output_lef_file = os.path.join(lef_dir, f"{top_name}_primitives.lef")
    combine_lefs(
        outdir=lef_dir,
        delete_file=output_lef_file
    )
    print("All processing completed successfully!")
    print(f"Converted {nfiles} GDS file(s)")
    print(f"LEF outputs available in {lef_dir}")
    print(f"Final combined LEF: {output_lef_file}")


if __name__ == "__main__":
    main()

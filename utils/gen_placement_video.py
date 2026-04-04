#!/usr/bin/env python3
import json, glob, os
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import imageio.v2 as imageio


def get_config():
    # -----------------------------
    # User configuration
    # -----------------------------
    SNAPSHOT_DIR = "snapshots"               # directory containing placement_step_*.json
    OUTPUT_GIF   = "placement_evolution.gif" # output animation file
    CHIP_W, CHIP_H = 0, 0                    # autodetect if 0
    FRAME_DURATION = 0.8                     # seconds per frame (lower = faster)
    SHOW_LABELS = True                       # display module names
    return SNAPSHOT_DIR, OUTPUT_GIF, CHIP_W, CHIP_H, FRAME_DURATION, SHOW_LABELS


def main():
    SNAPSHOT_DIR, OUTPUT_GIF, CHIP_W, CHIP_H, FRAME_DURATION, SHOW_LABELS = get_config()

    # -----------------------------
    # Load all snapshots
    # -----------------------------
    files = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "placement_step_*.json")))
    if not files:
        raise FileNotFoundError(f"No snapshot files found in {SNAPSHOT_DIR}/")

    print(f"Found {len(files)} snapshots.")

    # autodetect chip bounds
    max_x = max_y = 0
    for fname in files:
        data = json.load(open(fname))
        for mname, vals in data.items():
            x, y, w, h = vals["x"], vals["y"], vals["w"], vals["h"]
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
    if CHIP_W == 0:
        CHIP_W = max_x * 1.05
    if CHIP_H == 0:
        CHIP_H = max_y * 1.05

    # -----------------------------
    # Generate frames
    # -----------------------------
    frames = []
    for i, fname in enumerate(files):
        data = json.load(open(fname))
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.set_xlim(0, CHIP_W)
        ax.set_ylim(0, CHIP_H)
        ax.set_aspect("equal")
        ax.set_title(f"Placement Evolution ? Step {i+1}/{len(files)}", fontsize=13)

        for mname, vals in data.items():
            x, y, w, h = vals["x"], vals["y"], vals["w"], vals["h"]
            color = plt.cm.tab20(i % 20)
            ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor=color, linewidth=1.3))
            if SHOW_LABELS:
                ax.text(x + w/2, y + h/2, mname, ha='center', va='center', fontsize=6)

        plt.tight_layout()
        temp_png = f"_frame_{i:03d}.png"
        plt.savefig(temp_png, dpi=180)
        plt.close()
        frames.append(imageio.imread(temp_png))

    # -----------------------------
    # Save GIF
    # -----------------------------
    imageio.mimsave(OUTPUT_GIF, frames, duration=FRAME_DURATION)
    for f in glob.glob("_frame_*.png"):
        os.remove(f)

    print(f"\n? Placement evolution GIF saved as: {OUTPUT_GIF}")


if __name__ == "__main__":
    main()

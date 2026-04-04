#!/usr/bin/env python3
import json
import gdspy
import os
import sys
import shutil
import argparse



# Map clockwise orientations to degrees.
CW_TO_DEG = {0: 0, 1: 90, 2: 180, 3: 270}

# ===== Grid snapping (microns) =====
GRID = 0.005  # 5 nm in micron units (since GdsLibrary(unit=1e-6))
_EPS  = 1e-12

def snap(x, g=GRID):
    # round x to nearest multiple of grid, robust to small FP noise
    return round((x + _EPS) / g) * g

def snap_pt(pt, g=GRID):
    return (snap(pt[0], g), snap(pt[1], g))

def origin_for_ll_after_cw_rotation(xmin, ymin, xmax, ymax, rot_cw, target_x, target_y):
    """
    Return origin (ox, oy) so that AFTER a CW rotation by rot_cw*90 degrees
    the placed cell's bounding box lower left is exactly (target_x, target_y).

    CW mapping:
      R0:   (x, y) -> (x, y)
      R90:  (x, y) -> (y, -x)
      R180: (x, y) -> (-x, -y)
      R270: (x, y) -> (-y, x)
    """
    w = xmax - xmin
    h = ymax - ymin

    if rot_cw == 0:     # R0
        ox = target_x - xmin
        oy = target_y - ymin
        out_w, out_h = w, h

    elif rot_cw == 1:   # R90 CW: (x,y)->(y, -x)
        # LL_rot = (ymin, -xmax)
        ox = target_x - ymin
        oy = target_y + xmax
        out_w, out_h = h, w

    elif rot_cw == 2:   # R180 CW: (x,y)->(-x, -y)
        # LL_rot = (-xmax, -ymax)
        ox = target_x + xmax
        oy = target_y + ymax
        out_w, out_h = w, h

    elif rot_cw == 3:   # R270 CW: (x,y)->(-y, x)
        # LL_rot = (-ymax, xmin)
        ox = target_x + ymax
        oy = target_y - xmin
        out_w, out_h = h, w

    else:
        raise ValueError(f"Unsupported orientation code: {rot_cw}")

    return (ox, oy, out_w, out_h)

def _ensure_unique_dest_path(dst_dir, src_path, used_names):
    """Pick a unique filename in dst_dir for src_path, avoiding collisions."""
    base = os.path.basename(src_path)
    name, ext = os.path.splitext(base)
    candidate = base
    idx = 1
    while candidate in used_names:
        candidate = f"{name}_{idx}{ext}"
        idx += 1
    used_names.add(candidate)
    return os.path.join(dst_dir, candidate)

def _rebuild_snapped_cell_from_flat(flat_cell, grid=GRID, snapped_cell_name="TOP_SNAPPED"):
    snapped = gdspy.Cell(snapped_cell_name)

    # Extract polygons by (layer, datatype)
    by_spec = flat_cell.get_polygons(by_spec=True)

    for (layer, datatype), polys in by_spec.items():
        for poly in polys:
            snapped_poly = poly.copy()
            snapped_poly[:, 0] = (snapped_poly[:, 0] + _EPS) / grid
            snapped_poly[:, 0] = snapped_poly[:, 0].round() * grid
            snapped_poly[:, 1] = (snapped_poly[:, 1] + _EPS) / grid
            snapped_poly[:, 1] = snapped_poly[:, 1].round() * grid
            snapped.add(gdspy.Polygon(snapped_poly, layer=layer, datatype=datatype))

    # Labels: snap their positions and sanitize anchor
    valid_anchors = {
        'nw','top left','upper left','n','top center','upper center','ne','top right','upper right',
        'w','middle left','o','middle center','e','middle right',
        'sw','bottom left','lower left','s','bottom center','lower center','se','bottom right','lower right'
    }

    if flat_cell.labels:
        for lbl in flat_cell.labels:
            pos = snap_pt(lbl.position, grid)
            anchor = lbl.anchor
            # sanitize anchor
            if not isinstance(anchor, str) or anchor.lower() not in valid_anchors:
                anchor = 'o'  # default to middle center
            snapped.add(gdspy.Label(
                text=lbl.text,
                position=pos,
                anchor=anchor,
                rotation=lbl.rotation,
                magnification=lbl.magnification,
                layer=lbl.layer,
                texttype=lbl.texttype
            ))

    return snapped


def build_layout_from_json(json_file, out_gds="placed_layout.gds", scale=1000, copy_gds_to=None, snap_all_after_flat=True):
    # Load JSON (all coords are in same units as in JSON; divide by `scale` for microns)
    with open(json_file, "r") as f:
        data = json.load(f)

    # Snap chip size to grid
    chip_W = snap(float(data["chip"]["W"]) / scale)
    chip_H = snap(float(data["chip"]["H"]) / scale)

    # Create a library with micrometer units
    lib = gdspy.GdsLibrary(unit=1e-6, precision=1e-9)

    # We'll build initial geometry in a working top cell
    work_top = lib.new_cell("TOP")

    # Draw a chip outline for debugging on grid (this will be flattened & snapped anyway)
    outline = gdspy.Rectangle((0.0, 0.0), (chip_W, chip_H), layer=62, datatype=0)
    work_top.add(outline)

    # Prepare optional copy destination
    copied = []  # list of (src_abs, dst_abs)
    used_names = set()
    used_names_dummy = set()
    if copy_gds_to:
        os.makedirs(copy_gds_to, exist_ok=True)


    modules = data["modules"]

    for name, info in modules.items():
        gds_path = info.get("gds_file")
       # dummy_gds_path = info.get("dummy_gds_file")
        if not gds_path or not os.path.exists(gds_path):
            print(f"[WARN] {name}: missing GDS \"{gds_path}\", skipping.")
            continue

        # Optionally copy this primitive GDS
        if copy_gds_to:
            src_abs = os.path.abspath(gds_path)
            dst_abs = _ensure_unique_dest_path(copy_gds_to, src_abs, used_names)
            shutil.copy2(src_abs, dst_abs)
            copied.append((src_abs, dst_abs))


        # Load the primitive GDS into its own library
        sub_lib = gdspy.GdsLibrary(infile=gds_path)
        tops = sub_lib.top_level()
        if not tops:
            print(f"[WARN] {name}: \"{gds_path}\" has no top cells, skipping.")
            continue
        cell = tops[0]  # take first top cell

        bbox = cell.get_bounding_box()
        if bbox is None:
            print(f"[WARN] {name}: empty geometry in \"{gds_path}\", skipping.")
            continue
        (xmin, ymin), (xmax, ymax) = bbox

        rot_cw = int(info.get("orientation", 0))
        if rot_cw not in CW_TO_DEG:
            print(f"[WARN] {name}: bad orientation {rot_cw}, forcing R0.")
            rot_cw = 0

        # Target LL for the rotated bbox (scaled and snapped)
        x_target = snap(float(info["x"]) / scale)
        y_target = snap(float(info["y"]) / scale)

        # Compute origin so that rotated bbox LL = (x_target, y_target)
        ox, oy, out_w, out_h = origin_for_ll_after_cw_rotation(
            xmin, ymin, xmax, ymax, rot_cw, x_target, y_target
        )

        # Snap the origin to grid
        ox = snap(ox)
        oy = snap(oy)

        # Place reference (gdspy rotation is CCW; CW requires negative degrees)
        ref = gdspy.CellReference(
            cell,
            origin=(ox, oy),
            rotation=-CW_TO_DEG[rot_cw]  # negative for CW
        )
        work_top.add(ref)

        # Print placement summary using snapped values
        print(
            f"[PLACE] {name:>8s} | GDS=\"{gds_path}\" "
            f"| rot={CW_TO_DEG[rot_cw]} deg CW "
            f"| raw_bbox=({xmin:.6f},{ymin:.6f}) to ({xmax:.6f},{ymax:.6f}) "
            f"| origin=({ox:.6f},{oy:.6f}) "
            f"| final_bbox=({x_target:.6f},{y_target:.6f}) to ({snap(x_target+out_w):.6f},{snap(y_target+out_h):.6f})"
        )

    # Flatten references into raw geometry
    work_top.flatten()

    # Optionally: snap EVERY polygon vertex & label position after flattening
    if snap_all_after_flat:
        snapped_cell = _rebuild_snapped_cell_from_flat(work_top, grid=GRID, snapped_cell_name="TOP_SNAPPED")
        # Write only the snapped cell
        lib.add(snapped_cell)
        lib.write_gds(out_gds, cells=[snapped_cell])
        print(f"[INFO] Final snapped (post-flatten) layout written to {out_gds}")
    else:
        # No post-flatten snapping: write the flattened geometry as-is
        lib.write_gds(out_gds, cells=[work_top])
        print(f"[INFO] Final flattened layout (no snapping) written to {out_gds}")

    print(f"Total area of the chip {chip_W * chip_H} um^2")

    # Copy summary
    # if copy_gds_to and copied:
    #    print(f"[INFO] Copied {len(copied)} primitive GDS file(s) to: {os.path.abspath(copy_gds_to)}")
    #    for src, dst in copied:
    #        print(f"        {src}  ->  {dst}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a placed GDS layout from a placement JSON file."
    )

    # Required input
    parser.add_argument(
        "json_file",
        help="Path to the placement JSON file."
    )

    # Optional outputs / settings with same defaults as current script
    parser.add_argument(
        "-o", "--out-gds",
        default="placed_layout.gds",
        help='Output GDS file path. Default: "placed_layout.gds"'
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1000,
        help="Scaling factor to convert JSON coordinates to microns. Default: 1000"
    )
    parser.add_argument(
        "--copy-gds-to",
        default="FINAL/PRIMITIVES",
        help='Directory to copy primitive GDS files into. Default: "FINAL/PRIMITIVES"'
    )

    # Current default in your script is True
    parser.add_argument(
        "--no-snap-all-after-flat",
        dest="snap_all_after_flat",
        action="store_false",
        help="Disable post-flatten snapping of all polygons and labels."
    )
    parser.set_defaults(snap_all_after_flat=True)

    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.json_file):
        print(f'[ERROR] Placement JSON file not found: "{args.json_file}"')
        sys.exit(1)

    build_layout_from_json(
        json_file=args.json_file,
        out_gds=args.out_gds,
        scale=args.scale,
        copy_gds_to=args.copy_gds_to,
        snap_all_after_flat=args.snap_all_after_flat
    )


if __name__ == "__main__":
    main()

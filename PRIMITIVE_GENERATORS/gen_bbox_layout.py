import gdspy
import argparse
import os
import sys


def generate_bbox(input_gds, output_gds, new_name):
    """
    Read a GDS file, rename the top cell, shift its contents to the origin,
    and save into a new GDS file.

    Parameters
    ----------
    input_gds : str
        Path to the input GDS file.
    output_gds : str
        Path to the output GDS file with renamed cell.
    new_name : str
        New name to assign to the top cell.
    """
    # Clear any existing library
    gdspy.current_library = gdspy.GdsLibrary()

    # Load the input GDS
    lib = gdspy.GdsLibrary(infile=input_gds)

    # Get top-level cells
    top_cells = lib.top_level()
    if not top_cells:
        raise RuntimeError(f"No top-level cells found in {input_gds}")

    # Just take the first top-level cell
    top = top_cells[0]

    # Rename the cell
    old_name = top.name
    top.name = new_name
    lib.cells[new_name] = top
    if old_name in lib.cells:
        del lib.cells[old_name]

    # --- Shift contents to origin ---
    bbox = top.get_bounding_box()
    if bbox is None:
        raise ValueError("Top cell is empty ? nothing to shift")

    (x_min, y_min), _ = bbox
    dx, dy = -x_min, -y_min

    if dx != 0 or dy != 0:
        for poly in top.polygons:
            poly.translate(dx, dy)
        for path in top.paths:
            path.translate(dx, dy)
        for ref in top.references:
            ref.translate(dx, dy)
        for lbl in top.labels:
            try:
                lbl.translate(dx, dy)
            except AttributeError:
                lbl.position = (lbl.position[0] + dx, lbl.position[1] + dy)

    # Save the modified library
    lib.write_gds(output_gds)
    print(f"Saved {output_gds} with cell '{new_name}' shifted to origin.")

def parse_args():
    parser = argparse.ArgumentParser(
        description="PAD GDS renamer and origin shifter"
    )

    parser.add_argument(
        "--input_gds",
        type=str,
        required=True,
        help="Path to the input GDS file (required)"
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default ="examples",
        help="Directory where the output GDS will be written (default: examples)"
    )

    parser.add_argument(
        "--output_gds_name",
        type=str,
        default="pad_out.gds",
        help="Output GDS file name (default: pad_out.gds)"
    )

    parser.add_argument(
        "--new_name",
        type=str,
        default="bbox",
        help="New top cell name to assign (default: PAD)"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    output_gds = os.path.join(args.output_dir, args.output_gds_name)

    print("\n" + "=" * 80)
    print("Pad GDS renamer and origin shifter")
    print("=" * 80)
    print(f"Input GDS         : {args.input_gds}")
    print(f"Output directory  : {args.output_dir}")
    print(f"Output GDS name   : {args.output_gds_name}")
    print(f"New name          : {args.new_name}")
    print()
    print("=" * 80)

    if not os.path.exists(args.input_gds):
        raise FileNotFoundError(f"Input GDS file not found: {args.input_gds}")

    os.makedirs(args.output_dir, exist_ok=True)

    print("\nProcessing pad GDS...")
    generate_bbox(
        input_gds=args.input_gds,
        output_gds=output_gds,
        new_name=args.new_name
    )

    print("\nDone.")
    print(f"Generated file: {output_gds}")

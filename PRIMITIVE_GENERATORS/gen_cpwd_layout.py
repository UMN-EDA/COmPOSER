import gdspy
import sys
from matplotlib.path import Path
import numpy as np
import argparse
import os
from . import read_pdk
def move_shapes_for_symmetry_matching(rectangles, dx=0, dy=0):
    """
    Manually translate all gdspy.Rectangle objects by (dx, dy).
    Returns new Rectangle objects.
    """
    moved = []
    for rect in rectangles:
        # Get coordinates
        (llx, lly), (urx, ury) = rect.get_bounding_box()

        
        # Create a new rectangle with translated coordinates and same layer/datatype
        new_rect = gdspy.Rectangle(
            (llx + dx, lly + dy),
            (urx + dx, ury + dy),
            layer=rect.layers[0],
            datatype=rect.datatypes[0]
        )
        moved.append(new_rect)
    return moved

def insert_via(cell, ll, ur, layer_rules, via_name, via_layer_num=0, via_layer_datatype=0,
               move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False):
    print(f"Inserting via {via_layer_num} : {via_layer_datatype} in rectangle {ll} : {ur}")

    vencA_H = layer_rules[via_name]['VencA_H'] #0.2 for VIA7
    vencP_H = layer_rules[via_name]['VencP_H'] #0.2 for VIA7
    if ignore_venc:
        vencA_H = 0
        vencP_H = 0
    via_size = layer_rules[via_name]['WidthX'] #0.36 for VIA7
    via_pitch_x = layer_rules[via_name]['SpaceX'] #0.54 for VIA7
    via_pitch_y = layer_rules[via_name]['SpaceY'] #0.54 for VIA7

    vias = []
    final_x = 0
    final_y = 0

    y = ll[1] + vencP_H + user_y_buffer
    while y <= ur[1] - vencP_H - via_size + 1e-6:
        x = ll[0] + vencA_H + user_x_buffer
        while x <= ur[0] - vencA_H - via_size + 1e-6:
            vias.append(gdspy.Rectangle((x, y), (x + via_size, y + via_size),
                                        layer=via_layer_num, datatype=via_layer_datatype))
            final_x = x
            x += via_size + via_pitch_y
        final_y = y
        y += via_size + via_pitch_x

    # Compute leftover space for symmetry
    x_region_end = ur[0] - vencA_H
    y_region_end = ur[1] - vencP_H

    x_gap = x_region_end - (final_x + via_size)
    y_gap = y_region_end - (final_y + via_size)

    extra_x = max(x_gap, 0)
    extra_y = max(y_gap, 0)

    if move_for_symmetry:
        vias = move_shapes_for_symmetry_matching(vias, dx=extra_x / 2, dy=extra_y / 2)

    cell.add(vias)
    print(f"Placed {len(vias)} vias.")
    return cell

def insert_via_in_polygon(cell, polygon, via_layer_num=0, via_layer_datatype=0):
    """
    Insert vias inside an arbitrary polygon (not just a rectangle),
    ensuring they lie within the shape's boundaries.

    Args:
        cell (gdspy.Cell): Cell to which vias will be added.
        polygon (gdspy.Polygon or PolygonSet): Arbitrary shape.
        via_layer_num (int): GDS layer number.
        via_layer_datatype (int): GDS datatype.

    Returns:
        gdspy.Cell: Cell with vias added.
    """
    vencA_H = 0.2
    vencP_H = 0.2
    via_size = 0.36
    via_pitch = 0.54

    # Compute bounding box of the polygon
    (llx, lly), (urx, ury) = polygon.get_bounding_box()

    # Prepare via grid inside bounding box
    y = lly + vencP_H
    vias = []
    while y + via_size < ury - vencP_H:
        x = llx + vencA_H
        while x + via_size < urx - vencA_H:
            # Define a candidate via
            via_rect = gdspy.Rectangle((x, y), (x + via_size, y + via_size),
                                       layer=via_layer_num, datatype=via_layer_datatype)
            # Check if via center lies inside the original shape
            center_x = x + via_size / 2
            center_y = y + via_size / 2
            # polygon is a PolygonSet, so check each sub-polygon
            is_inside = any(
                Path(pts).contains_point((center_x, center_y))
                for pts in polygon.polygons
            )

            if is_inside:
                vias.append(via_rect)
            x += via_size + via_pitch
        y += via_size + via_pitch

    # Optional: compute leftover space and center the via array
    extra_x = (urx - llx) % (via_size + via_pitch)
    extra_y = (ury - lly) % (via_size + via_pitch)
    vias = move_shapes_for_symmetry_matching(vias, dx=extra_x / 2, dy=extra_y / 2)

    cell.add(vias)
    print(f"Placed {len(vias)} vias.")
    return cell

def create_cpwd(
    length,
    width,
    gap,
    gds_name,
    gds_dir,
    layer_datatypes, 
    layer_num, 
    label_layers, 
    layer_rules
):

    # Create a new cell for the capacitor
    cpwd = gdspy.Cell(f"{gds_name}_dummy")
    gdspy.unit = 1e-6  # This is the default
    # Set the database grid precision to 1.0 = 1 nanometer
    gdspy.precision = 1e-9 # This is the default
    #Middle M9 strip
    mid_M9 = gdspy.Rectangle(
                    (0, 0),
                    (length, width),
                    layer=layer_num['M9'],
                    datatype=layer_datatypes['M9']['Draw']
                )
    cpwd.add(mid_M9)
    #top M9 strip
    top_M9 = gdspy.Rectangle(
                    (0, width+gap),
                    (length, width+width + gap - 1),
                    layer=layer_num['M9'],
                    datatype=layer_datatypes['M9']['Draw']
                )
    cpwd.add(top_M9)
    #bottom M9 strip
    bottom_M9 = gdspy.Rectangle(
                    (0, -(width+gap-1)),
                    (length, -(gap)),
                    layer=layer_num['M9'],
                    datatype=layer_datatypes['M9']['Draw']
                )
    cpwd.add(bottom_M9)

    #Check for Length and number of Vertical rails it can accomodate
    #Each rail fo width = 2um and spacing=1um
    rail_width = 2
    rail_spacing = 1
    num_rails = int(length / (rail_width + rail_spacing))
    print(f"Number of rails {num_rails}")
    #But we need 1 extra on each ends
    num_rails = num_rails + 2
    effective_length = num_rails * (rail_width + rail_spacing)
    extra_length = effective_length - length - rail_spacing #1 spacing has to be ignored

    #top M9 and M8 strip_thin
    top_M9_thin = gdspy.Rectangle(
                    (0 - extra_length/2, 2*width+gap - 2.9),
                    (length + extra_length/2, 2* width + gap),
                    layer=layer_num['M9'],
                    datatype=layer_datatypes['M9']['Draw']
                )
    cpwd.add(top_M9_thin)
    top_M8_thin = gdspy.Rectangle(
                    (0 - extra_length/2, 2*width+gap - 2.9),
                    (length + extra_length/2, 2* width + gap),
                    layer=layer_num['M8'],
                    datatype=layer_datatypes['M8']['Draw']
                )
    cpwd.add(top_M8_thin)

    #bottom M9 strip_thin
    bottom_M9_thin = gdspy.Rectangle(
                    (0 - extra_length/2, -(width+gap)),
                    (length + extra_length/2, -(width + gap - 2.9)),
                    layer=layer_num['M9'],
                    datatype=layer_datatypes['M9']['Draw']
                )
    cpwd.add(bottom_M9_thin)
    bottom_M8_thin = gdspy.Rectangle(
                    (0 - extra_length/2, -(width+gap)),
                    (length + extra_length/2, -(width + gap - 2.9)),
                    layer=layer_num['M8'],
                    datatype=layer_datatypes['M8']['Draw']
                )
    cpwd.add(bottom_M8_thin)

    bottom_via_box = bottom_M8_thin.get_bounding_box()
    top_via_box = top_M8_thin.get_bounding_box()
    #Adding vertical rails
    start_x = -extra_length/2
    for i in range(num_rails):
        step = rail_spacing + rail_width
        rail = gdspy.Rectangle(
                    (i*(step) + start_x , bottom_via_box[0][1]),
                    (i*(step) + start_x + rail_width, top_via_box[1][1]),
                    layer=layer_num['M8'],
                    datatype=layer_datatypes['M8']['Draw']
                )
        cpwd.add(rail)

    #Adding VIA8 on the bottom strip
    cpwd = insert_via(cpwd, ll = bottom_via_box[0], ur=bottom_via_box[1], layer_rules=layer_rules, via_name="V8", 
                      via_layer_num=layer_num["V8"], via_layer_datatype=layer_datatypes['V8']['Draw'], move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False)

    #Adding VIA8 on the top strip
    cpwd = insert_via(cpwd, ll = top_via_box[0], ur= top_via_box[1], layer_rules=layer_rules, via_name="V8", 
                      via_layer_num=layer_num["V8"], via_layer_datatype=layer_datatypes['V8']['Draw'], move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False)

    #Adding P1, P2, GND labels
    #GND1
    cpwd.add(gdspy.Rectangle(
        (0 + length/2 - width/2, -(width+gap-1)),
        (0 + length/2 + width/2, -(gap)),
        layer=label_layers[layer_num['M9']][0],              # layer number
        datatype=label_layers[layer_num['M9']][1]             # NOT datatype! this is texttype field
    ))
    cpwd.add(gdspy.Label(
        text="GND1",
        position=(length/ 2, (-width - gap + 1)),
        anchor='s',           # southwest anchor
        layer=label_layers[layer_num['M9']][0],              # layer number
        texttype=label_layers[layer_num['M9']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))
    #GND2
    cpwd.add(gdspy.Rectangle(
        (0 + length/2 - width/2, width+gap),
        (0 + length/2 + width/2, width+width + gap - 1),
        layer=label_layers[layer_num['M9']][0],              # layer number
        datatype=label_layers[layer_num['M9']][1]             # NOT datatype! this is texttype field
    ))
    cpwd.add(gdspy.Label(
        text="GND2",
        position=(length/ 2, (width+width + gap - 1)),
        anchor='n',           # southwest anchor
        layer=label_layers[layer_num['M9']][0],              # layer number
        texttype=label_layers[layer_num['M9']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))
    #P1
    cpwd.add(gdspy.Rectangle(
        (0, 0),
        (width, width),
        layer=label_layers[layer_num['M9']][0],              # layer number
        datatype=label_layers[layer_num['M9']][1]             # NOT datatype! this is texttype field
    ))
    cpwd.add(gdspy.Label(
        text="P1",
        position=(0, (width/2)),
        anchor='n',           # southwest anchor
        layer=label_layers[layer_num['M9']][0],              # layer number
        texttype=label_layers[layer_num['M9']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))
    #P2
    cpwd.add(gdspy.Rectangle(
        (length-width, 0),
        (length, width),
        layer=label_layers[layer_num['M9']][0],              # layer number
        datatype=label_layers[layer_num['M9']][1]             # NOT datatype! this is texttype field
    ))
    cpwd.add(gdspy.Label(
        text="P2",
        position=(length, (width/2)),
        anchor='e',           # southwest anchor
        layer=label_layers[layer_num['M9']][0],              # layer number
        texttype=label_layers[layer_num['M9']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))

    bbox = cpwd.get_bounding_box()
    if bbox is not None:
        llx, lly = bbox[0]
        dx, dy = -llx, -lly
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    cpwd_to_export = gdspy.Cell(f'{gds_name}')
    cpwd_to_export.add(gdspy.CellReference(cpwd, (dx, dy)))

    out_path = os.path.join(gds_dir, f"{gds_name}.gds")
    gdspy.write_gds(out_path, cells = [cpwd, cpwd_to_export])

    # return mim_cap_cell

def parse_args():
    parser = argparse.ArgumentParser(
        description="CPWD GDS GENERATOR"
    )

    parser.add_argument(
        "--pdk",
        type=str,
        required=True,
        help="Path to the PDK layers.json file (required)"
    )

    parser.add_argument(
        "--length", "-l",
        type=float,
        default=100.0,
        help="CPWD length in um (default: 100.0)"
    )

    parser.add_argument(
        "--width", "-w",
        type=float,
        default=12.0,
        help="Center conductor width in um (default: 12.0)"
    )

    parser.add_argument(
        "--gap", "-g",
        type=float,
        default=2.0,
        help="Gap in um (default: 2.0)"
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default="examples",
        help="Directory where the output GDS will be written (default: examples)"
    )

    parser.add_argument(
        "--output_gds_name",
        type=str,
        default="cpwd",
        help="Output GDS base name without extension (default: cpwd)"
    )
    parser.add_argument("--scale", "-s", type=float, default=1000.0,
                        help="Scaling factor (default: 1000)")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 80)
    print("CPWD GDS generator")
    print("=" * 80)
    print(f"PDK file           : {args.pdk}")
    print(f"Length (um)        : {args.length}")
    print(f"Width (um)         : {args.width}")
    print(f"Gap (um)           : {args.gap}")
    print(f"Output directory   : {args.output_dir}")
    print(f"Output GDS name    : {args.output_gds_name}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name} --pdk /path/to/layers.json")
    print(f"  Custom  : python {script_name} --pdk /path/to/layers.json --length 200 --width 10 --gap 3 --output_dir PRIMITIVES --output_gds_name my_cpwd")
    print("=" * 80)

    if not os.path.exists(args.pdk):
        raise FileNotFoundError(f"PDK file not found: {args.pdk}")

    os.makedirs(args.output_dir, exist_ok=True)

    print("\nReading PDK layer information...")
    layer_datatypes, layer_num, label_layers, layer_rules, design_info = read_pdk.readLayerInfo(args.pdk, scale=args.scale)
    print("PDK layer information loaded successfully.")

    print("\nGenerating CPWD layout...")
    create_cpwd(
        length=args.length,
        width=args.width,
        gap=args.gap,
        gds_name=args.output_gds_name,
        gds_dir=args.output_dir,
        layer_datatypes=layer_datatypes,
        layer_num=layer_num,
        label_layers=label_layers,
        layer_rules=layer_rules
    )

    print("\nDone.")
    print(f"Generated file: {os.path.join(args.output_dir, args.output_gds_name + '.gds')}")

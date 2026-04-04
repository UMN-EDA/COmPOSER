import gdspy
from . import read_pdk
import sys
from matplotlib.path import Path
import numpy as np
import argparse
import os

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
    #print(f"Inserting via {via_layer_num} : {via_layer_datatype} in rectangle {ll} : {ur}")

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
    #print(f"Placed {len(vias)} vias.")
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

def create_poly_res(
    length,
    width,
    gds_name,
    gds_dir,
    layer_datatypes, 
    layer_num, 
    label_layers, 
    layer_rules
):

    # Create a new cell for the capacitor
    poly_res = gdspy.Cell(gds_name)
    gdspy.unit = 1e-6  # This is the default
    # Set the database grid precision to 1.0 = 1 nanometer
    gdspy.precision = 1e-9 # This is the default
    #CTM for mim cap
    po_buffer = 0.34
    po_rect = gdspy.Rectangle(
                    (0, 0),
                    (length + 2*po_buffer , width),
                    layer=layer_num['Poly'],
                    datatype=layer_datatypes['Poly']['Draw']
                )
    poly_res.add(po_rect)
    po_bbox = po_rect.get_bounding_box()

    pp_buffer = 0.2
    pp_rect = gdspy.Rectangle(
                    (po_bbox[0][0] - pp_buffer, po_bbox[0][1] - pp_buffer),
                    (po_bbox[1][0] + pp_buffer, po_bbox[1][1] + pp_buffer),
                    layer=layer_num['PP'],
                    datatype=layer_datatypes['PP']['Draw']
                )
    poly_res.add(pp_rect)
    rpo_vert_buffer = 0.22
    rpo_rect = gdspy.Rectangle(
                    (po_bbox[0][0] + po_buffer, po_bbox[0][1] - rpo_vert_buffer),
                    (po_bbox[1][0] - po_buffer, po_bbox[1][1] + rpo_vert_buffer),
                    layer=layer_num['RPO'],
                    datatype=layer_datatypes['RPO']['Draw']
                )
    poly_res.add(rpo_rect)

    m1_left = 0.03 
    m1_top = 0.015 
    m1_thickness = 0.09
    #Drop vias
    poly_res = insert_via(poly_res, ll = (po_bbox[0][0] + m1_left, po_bbox[0][1] + m1_top), ur= (po_bbox[0][0] + m1_left + m1_thickness, po_bbox[1][1] - m1_top), layer_rules=layer_rules, via_name="V0", via_layer_num=layer_num["V0"], via_layer_datatype=layer_datatypes['V0']['Draw'], move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = True)

    #Drop vias
    poly_res = insert_via(poly_res, ll = (po_bbox[1][0] - m1_left - m1_thickness, po_bbox[0][1] + m1_top), ur= (po_bbox[1][0] - m1_left , po_bbox[1][1] - m1_top), layer_rules=layer_rules, via_name="V0", via_layer_num=layer_num["V0"], via_layer_datatype=layer_datatypes['V0']['Draw'], move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = True)

    #Metal shorts
    m1_left_strip = gdspy.Rectangle(
                    (po_bbox[0][0] + m1_left, po_bbox[0][1] + m1_top),
                    (po_bbox[0][0] + m1_left + m1_thickness, po_bbox[1][1] - m1_top),
                    layer=layer_num['M1'],
                    datatype=layer_datatypes['M1']['Draw']
                )
    poly_res.add(m1_left_strip)

    m1_right_strip = gdspy.Rectangle(
                    (po_bbox[1][0] - m1_left- m1_thickness, po_bbox[0][1] + m1_top),
                    (po_bbox[1][0] - m1_left , po_bbox[1][1] - m1_top),
                    layer=layer_num['M1'],
                    datatype=layer_datatypes['M1']['Draw']
                )
    poly_res.add(m1_right_strip)

    rpdmy_box = gdspy.Rectangle(
                    (po_bbox[0][0] + po_buffer, po_bbox[0][1]),
                    (po_bbox[1][0] - po_buffer , po_bbox[1][1]),
                    layer=layer_num['RPDMY'],
                    datatype=layer_datatypes['RPDMY']['Draw']
                )
    poly_res.add(rpdmy_box)

    rh_box = gdspy.Rectangle(
                    (po_bbox[0][0] - pp_buffer, po_bbox[0][1] - pp_buffer),
                    (po_bbox[1][0] + pp_buffer , po_bbox[1][1] + pp_buffer),
                    layer=layer_num['RH'],
                    datatype=layer_datatypes['RH']['Draw']
                )
    poly_res.add(rh_box)
    poly_res.add(gdspy.Rectangle(
        (po_bbox[0][0] + m1_left, (po_bbox[0][1] + po_bbox[1][1])/2 - width/2),
        (po_bbox[0][0] + m1_left + m1_thickness, (po_bbox[0][1] + po_bbox[1][1])/2 + width/2),
        layer=label_layers[layer_num['M1']][0],              # layer number
        datatype=label_layers[layer_num['M1']][1]             # NOT datatype! this is texttype field
    ))
    poly_res.add(gdspy.Label(
        text="PLUS",
        position=((po_bbox[0][0] + m1_left + po_bbox[0][0] + m1_left )/ 2, (po_bbox[0][1] + 2*m1_top + po_bbox[1][1] )/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M1']][0],              # layer number
        texttype=label_layers[layer_num['M1']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))

    poly_res.add(gdspy.Rectangle(
        (po_bbox[1][0] - m1_left- m1_thickness, (po_bbox[0][1] + po_bbox[1][1] )/2 - width/2),
        (po_bbox[1][0] - m1_left ,  (po_bbox[0][1] + po_bbox[1][1] )/2 + width/2),
        layer=label_layers[layer_num['M1']][0],              # layer number
        datatype=label_layers[layer_num['M1']][1]             # NOT datatype! this is texttype field
    ))
    poly_res.add(gdspy.Label(
        text="MINUS",
        position=((po_bbox[1][0] - m1_left + po_bbox[1][0] - m1_left )/ 2, (po_bbox[0][1] + 2*m1_top + po_bbox[1][1] )/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M1']][0],              # layer number
        texttype=label_layers[layer_num['M1']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))

    # Align to (0,0) by translating all shapes in-place
    bbox = poly_res.get_bounding_box()
    if bbox is not None:
        (x_min, y_min), _ = bbox
        for poly in poly_res.polygons:
            poly.translate(-x_min, -y_min)
        for path in poly_res.paths:
            path.translate(-x_min, -y_min)
        for ref in poly_res.references:
            ref.translate(-x_min, -y_min)
        for lbl in poly_res.labels:
            lbl.translate(-x_min, -y_min)


    #print("Shifted cell to origin. New bbox:", poly_res.get_bounding_box())



    out_path = os.path.join(gds_dir, f"{gds_name}.gds")
    gdspy.write_gds(out_path, cells=[poly_res])
    # return mim_cap_cell

# --- Main execution block ---
def parse_args():
    parser = argparse.ArgumentParser(
        description="POLY RESISTOR GENERATOR"
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
        default=10.0,
        help="Poly resistor length in um (default: 10.0)"
    )

    parser.add_argument(
        "--width", "-w",
        type=float,
        default=10.0,
        help="Poly resistor width in um (default: 10.0)"
    )

    parser.add_argument(
        "--name",
        type=str,
        default="poly_res",
        help="Output GDS base name (default: poly_res)"
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default="examples",
        help="Directory to write the output GDS file (default: current directory)"
    )
    parser.add_argument("--scale", "-s", type=float, default=1000.0,
                        help="Scaling factor (default: 1000)")

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 80)
    print("Poly resistor GDS generator")
    print("=" * 80)
    print(f"PDK file         : {args.pdk}")
    print(f"Length (um)      : {args.length}")
    print(f"Width (um)       : {args.width}")
    print(f"GDS name         : {args.name}")
    print(f"Output directory : {args.output_dir}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name} --pdk /path/to/layers.json")
    print(f"  Custom  : python {script_name} --pdk /path/to/layers.json --length 20 --width 2 --name my_poly_res")
    print("=" * 80)

    if not os.path.exists(args.pdk):
        raise FileNotFoundError(f"PDK file not found: {args.pdk}")

    os.makedirs(args.output_dir, exist_ok=True)

    print("\nReading PDK layer information...")
    layer_datatypes, layer_num, label_layers, layer_rules, design_info = read_pdk.readLayerInfo(args.pdk, scale=args.scale)
    print("PDK layer information loaded successfully.")

    print("\nGenerating poly resistor layout...")
    create_poly_res(
        length=args.length,
        width=args.width,
        gds_name=args.name,
        gds_dir=args.output_dir,
        layer_datatypes=layer_datatypes,
        layer_num=layer_num,
        label_layers=label_layers,
        layer_rules=layer_rules
    )

    print("\nDone.")
    print(f"GDS written to: {os.path.join(args.output_dir, args.name + '.gds')}")

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
    #print(f"Inserting via {via_layer_num} : {via_layer_datatype} in rectangle {ll} : {ur}")

    vencA_H = layer_rules[via_name]['VencA_H'] #0.2 for VIA7
    vencP_H = layer_rules[via_name]['VencP_H'] #0.2 for VIA7
    if ignore_venc:
        vencA_H = 0
        vencP_H = 0
    via_size = layer_rules[via_name]['WidthX'] #0.36 for VIA7
    via_pitch_x = layer_rules[via_name]['SpaceX'] #Special case for CAP only
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
            x += via_size + via_pitch_x
        final_y = y
        y += via_size + via_pitch_y

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
    #print(f"Placed {len(vias)} vias.")
    return cell

def extract_cell_details(
    cell,
    pin_layers=[(131, 0), (132, 0), (133, 0), (134, 0), (135, 0), (136, 0), (137, 0), (138, 0), (139, 0)],
    pin_order=None
):
    """
    Extract cell bounding box and pin locations (with names, bbox, and label center) 
    from a gdspy.GdsLibrary object.

    Args:
        lib (gdspy.GdsLibrary): A GdsLibrary object already loaded.
        pin_layers (list of tuple): List of (layer, datatype) tuples where pins are drawn.
        pin_order (list of str, optional): Desired ordering of pin names. If provided,
                                           output pins will follow this order.

    Returns:
        (bbox, w, h, pins):
            bbox (tuple): (x0, y0, x1, y1) absolute bounding box of cell
            w (float): width of cell
            h (float): height of cell
            pins (list of dict): 
                [
                  {
                    "name": str,
                    "layer": int,
                    "datatype": int,
                    "bbox": (px0, py0, px1, py1),
                    "cx": float,   # pin bbox center
                    "cy": float,
                    "lx": float,   # label anchor
                    "ly": float
                  },
                  ...
                ]
    """
    topcell = cell

    # --- bounding box of the entire cell ---
    all_polys = []
    for polys in topcell.get_polygons(by_spec=True).values():
        all_polys.extend(polys)
    if not all_polys:
        raise ValueError("No polygons found in topcell")

    all_points = [pt for poly in all_polys for pt in poly]
    x_coords, y_coords = zip(*all_points)
    x0, y0, x1, y1 = min(x_coords), min(y_coords), max(x_coords), max(y_coords)
    w, h = float(x1 - x0), float(y1 - y0)

    # --- collect text labels (for pin names) ---
    texts = [(lbl.text, float(lbl.position[0]), float(lbl.position[1])) for lbl in topcell.get_labels()]

    # --- pin extraction ---
    pins = []
    spec_map = topcell.get_polygons(by_spec=True)

    for layer in pin_layers:
        for poly in spec_map.get(layer, []):
            px0, py0 = poly.min(axis=0)
            px1, py1 = poly.max(axis=0)
            cx, cy = (float((px0 + px1) / 2), float((py0 + py1) / 2))

            # find nearest label for pin name
            name, lx, ly = None, None, None
            if texts:
                dists = [(abs(cx - tx) + abs(cy - ty), txt, tx, ty) for txt, tx, ty in texts]
                dmin, name, lx, ly = min(dists, key=lambda x: x[0])

            pins.append({
                "name": name,
                "layer": layer[0],
                "datatype": layer[1],
                "bbox": (float(px0), float(py0), float(px1), float(py1)),
                "cx": cx,
                "cy": cy,
                "lx": lx,
                "ly": ly
            })

    # --- reorder pins if pin_order is given ---
    if pin_order:
        name_to_pins = {}
        for p in pins:
            if p["name"] is not None:
                name_to_pins.setdefault(p["name"], []).append(p)

        ordered = []
        for n in pin_order:
            if n in name_to_pins:
                ordered.extend(name_to_pins[n])  # keep all pins with this name

        remaining = [p for p in pins if p["name"] not in pin_order]
        pins = ordered + remaining

    return (x0, y0, x1, y1), w, h, pins

def generate_casmos(
    length: float =10.0,
    fw: float = 10.0,
    nf: float = 2.0,
    dummy = 2,
    layer_datatypes = None,
    layer_num = None,
    label_layers = None, 
    layer_rules = None,
    output_dir = None,
    output_gds = None,
    if_cell_details = False
):

    casmos = gdspy.Cell(f"{output_gds}_dummy")
    gdspy.unit = 1e-6  # This is the default
    # Set the database grid precision to 1.0 = 1 nanometer
    gdspy.precision = 0.005e-6 # This is the default

    m1_m2_gap_orig = 0.69

    m1_strip_width = 0.18
    #OD  (Active)
    #M1
    od_offset = 0.195
    poly_pitch = 0.22
    od_top = gdspy.Rectangle(
            (0, 0),
            ((nf+1)*(length + poly_pitch) + 2*od_offset + length, fw),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(od_top)
    od_top_bbox = od_top.get_bounding_box()

    shield_x_offset = 0.47
    shield_width = 0.21
    od_top_left_shield =  gdspy.Rectangle(
            (od_top_bbox[0][0]-shield_x_offset, 0),
            (od_top_bbox[0][0]-shield_x_offset + shield_width, fw),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(od_top_left_shield)
    casmos = insert_via(cell=casmos, ll=od_top_left_shield.get_bounding_box()[0], ur=od_top_left_shield.get_bounding_box()[1],
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    pp_box_gap = 0.13
    pp_top_left_box = gdspy.Rectangle(
            (od_top_bbox[0][0]-shield_x_offset - pp_box_gap , 0-pp_box_gap),
            (od_top_bbox[0][0]-shield_x_offset + shield_width+pp_box_gap, fw+pp_box_gap),
            layer=layer_num['PP'],
            datatype=layer_datatypes['PP']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(pp_top_left_box)

    od_top_right_shield =  gdspy.Rectangle(
            (od_top_bbox[1][0]+shield_x_offset - shield_width, 0),
            (od_top_bbox[1][0]+shield_x_offset , fw),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(od_top_right_shield)
    casmos = insert_via(cell=casmos, ll=od_top_right_shield.get_bounding_box()[0], ur=od_top_right_shield.get_bounding_box()[1],
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    pp_top_right_box = gdspy.Rectangle(
            (od_top_bbox[1][0]+shield_x_offset - shield_width - pp_box_gap, 0-pp_box_gap),
            (od_top_bbox[1][0]+shield_x_offset +pp_box_gap, fw+pp_box_gap),
            layer=layer_num['PP'],
            datatype=layer_datatypes['PP']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(pp_top_right_box)
    m1_m2_gap = m1_m2_gap_orig + od_top_bbox[1][1]
    #M2
    od_bottom = gdspy.Rectangle(
            (0, -m1_m2_gap),
            ((nf+1)*(length + poly_pitch) + 2*od_offset + length, fw-m1_m2_gap),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(od_bottom)
    od_bottom_bbox = od_bottom.get_bounding_box()   
    od_bottom_left_shield =  gdspy.Rectangle(
            (od_bottom_bbox[0][0]-shield_x_offset, 0-m1_m2_gap),
            (od_bottom_bbox[0][0]-shield_x_offset + shield_width, fw-m1_m2_gap),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(od_bottom_left_shield)
    casmos = insert_via(cell=casmos, ll=od_bottom_left_shield.get_bounding_box()[0], ur=od_bottom_left_shield.get_bounding_box()[1],
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    pp_bottom_left_box = gdspy.Rectangle(
            (od_bottom_bbox[0][0]-shield_x_offset - pp_box_gap, 0-m1_m2_gap - pp_box_gap),
            (od_bottom_bbox[0][0]-shield_x_offset + shield_width + pp_box_gap, fw-m1_m2_gap + pp_box_gap),
            layer=layer_num['PP'],
            datatype=layer_datatypes['PP']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(pp_bottom_left_box)
    od_bottom_right_shield =  gdspy.Rectangle(
            (od_bottom_bbox[1][0]+shield_x_offset - shield_width, 0-m1_m2_gap),
            (od_bottom_bbox[1][0]+shield_x_offset , fw-m1_m2_gap),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(od_bottom_right_shield)
    pp_bottom_right_box = gdspy.Rectangle(
            (od_bottom_bbox[1][0]+shield_x_offset - shield_width - pp_box_gap, 0-m1_m2_gap - pp_box_gap),
            (od_bottom_bbox[1][0]+shield_x_offset + pp_box_gap, fw-m1_m2_gap + pp_box_gap),
            layer=layer_num['PP'],
            datatype=layer_datatypes['PP']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(pp_bottom_right_box)
    casmos = insert_via(cell=casmos, ll=od_bottom_right_shield.get_bounding_box()[0], ur=od_bottom_right_shield.get_bounding_box()[1],
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    left_joint_shield = gdspy.Rectangle(
            (od_bottom_left_shield.get_bounding_box()[0][0], od_bottom_left_shield.get_bounding_box()[1][1] + 0.02),
            (od_top_left_shield.get_bounding_box()[1][0], od_top_left_shield.get_bounding_box()[0][1] - 0.02),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(left_joint_shield)
    casmos = insert_via(cell=casmos, ll=left_joint_shield.get_bounding_box()[0], ur=left_joint_shield.get_bounding_box()[1],
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    right_joint_shield = gdspy.Rectangle(
            (od_bottom_right_shield.get_bounding_box()[0][0], od_bottom_right_shield.get_bounding_box()[1][1] + 0.02),
            (od_top_right_shield.get_bounding_box()[1][0], od_top_right_shield.get_bounding_box()[0][1] - 0.02),
            layer=layer_num['Active'],
            datatype=layer_datatypes['Active']['Draw'] #OD is same as ACTIVE
        )
    casmos.add(right_joint_shield)
    casmos = insert_via(cell=casmos, ll=right_joint_shield.get_bounding_box()[0], ur=right_joint_shield.get_bounding_box()[1],
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    #Poly
    #M1
    poly_short_top_m1 = True
    poly_short_bottom_m1 = False
    if poly_short_top_m1 == True:
        poly_up_offset_m1 = 0.1
    else:
        poly_up_offset_m1 = 0.14
    if poly_short_bottom_m1 == True:
        poly_down_offset_m1 = 0.1
    else:
        poly_down_offset_m1 = 0.14
    metal_list = ['M1', 'M2', 'M3']
    via_list = ['V0', 'V1', 'V2']
    metal_list.append('M4')
    via_list.append('V3')
    metal_list_temp = metal_list + ['M5']
    via_list_temp = via_list + ['V4']
    m1_box = gdspy.Rectangle(
            (od_top_bbox[0][0]-0.005, od_top_bbox[0][1]-0.02),(od_top_bbox[0][0] + m1_strip_width - 0.005, od_top_bbox[1][1] + 0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
        )
    left_most_drain = ((od_top_bbox[0][0]-0.005, od_top_bbox[0][1]-0.02),(od_top_bbox[0][0] + m1_strip_width - 0.005, od_top_bbox[1][1] + 0.02))
    casmos.add(m1_box)
    casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
    if nf %2 == 0:
        m2_box = gdspy.Rectangle(
                    (od_top_bbox[1][0] - m1_strip_width + 0.005,od_top_bbox[0][1] - 0.02),(od_top_bbox[1][0]+0.005, od_top_bbox[1][1]+0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
                )
        casmos.add(m2_box)
        right_most_drain = ((od_top_bbox[1][0] - m1_strip_width + 0.005,od_top_bbox[0][1] - 0.02),(od_top_bbox[1][0]+0.005, od_top_bbox[1][1]+0.02))
        casmos = insert_via(cell=casmos, ll=m2_box.get_bounding_box()[0], ur=m2_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
    for m, v in zip(metal_list_temp, via_list_temp):
        m1_box = gdspy.Rectangle(
                (od_top_bbox[0][0]-0.005, od_top_bbox[0][1]-0.02),(od_top_bbox[0][0] + m1_strip_width - 0.005, od_top_bbox[1][1] + 0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            )
        casmos.add(m1_box)
        casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
        
        m2_box = gdspy.Rectangle(
                (od_top_bbox[1][0] - m1_strip_width + 0.005,od_top_bbox[0][1] - 0.02),(od_top_bbox[1][0]+0.005, od_top_bbox[1][1]+0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            )
        casmos.add(m2_box)
        casmos = insert_via(cell=casmos, ll=m2_box.get_bounding_box()[0], ur=m2_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)

    if nf%2 == 0:
        casmos = insert_via(cell=casmos, ll=m2_box.get_bounding_box()[0], ur=m2_box.get_bounding_box()[1],
                                    layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
    if nf % 2 != 0 :
        
        m1_box = gdspy.Rectangle(
            (od_top_bbox[1][0] - m1_strip_width + 0.005,od_top_bbox[0][1] - 0.02 - m1_m2_gap_orig + 0.04),(od_top_bbox[1][0]+0.005, od_top_bbox[1][1]+0.02),layer=layer_num['M4'], datatype=layer_datatypes['M4']['Draw']
        )
        casmos.add(m1_box)
        m1_box = gdspy.Rectangle(
            (od_top_bbox[1][0] - m1_strip_width + 0.005,od_top_bbox[0][1] - 0.02 - m1_m2_gap_orig + 0.04),(od_top_bbox[1][0]+0.005, od_top_bbox[1][1]+0.02),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
        )
        casmos.add(m1_box)
    for f in range(nf + dummy):
        ll = od_top_bbox[0]
        ur = od_top_bbox[1]

        poly = gdspy.Rectangle(
            (ll[0]+ od_offset + f*(poly_pitch + length) , ll[1] - poly_down_offset_m1 ),
            ((ll[0]+ od_offset + f*(poly_pitch + length) + length, ur[1] + poly_up_offset_m1)),
            layer=layer_num['Poly'],
            datatype=layer_datatypes['Poly']['Draw'] 
        )
        casmos.add(poly)
        
        poly_bbox = poly.get_bounding_box()
        if f < (nf + dummy - 1):
            
            for m, v in zip(metal_list_temp, via_list_temp):
                if f % 2 == 0:
                    ll_elongation = m1_m2_gap_orig - 0.04
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_top_bbox[0][1]-0.02 - ll_elongation),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) - 0.02, od_top_bbox[0][1]-0.02),layer=layer_num['M4'], datatype=layer_datatypes['M4']['Draw']
                    )
                    casmos.add(m1_box)
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_top_bbox[0][1]-0.02 - ll_elongation),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) - 0.02, od_top_bbox[0][1]-0.02),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
                    )
                    casmos.add(m1_box)
                m1_box = gdspy.Rectangle(
                    (poly_bbox[1][0] + 0.02, od_top_bbox[0][1]-0.02),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) - 0.02, od_top_bbox[1][1]+0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
                )
                casmos.add(m1_box)

                if f % 2 != 0:
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_top_bbox[0][1]-0.02),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) - 0.02, od_top_bbox[1][1]+0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
                    )
                    casmos.add(m1_box)
                    if nf%2 != 0:
                        right_most_drain = ((poly_bbox[1][0] + 0.02, od_top_bbox[0][1]-0.02),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) - 0.02, od_top_bbox[1][1]+0.02))
                    casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur = m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
                    casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur = m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
                casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur = m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
            
    
    # casmos.add(m1_box)
    #SS
    m7_ss_extension = 1.165
    casmos.add(gdspy.Rectangle((left_most_drain[0][0]-m7_ss_extension, left_most_drain[0][1]),right_most_drain[1],layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']))
    casmos.add(gdspy.Rectangle(
        (left_most_drain[0][0]-m7_ss_extension, left_most_drain[0][1]),
        (left_most_drain[0][0]-m7_ss_extension + 0.3, right_most_drain[1][1]),
        layer=label_layers[layer_num['M7']][0],              # layer number
        datatype=label_layers[layer_num['M7']][1]             # NOT datatype! this is texttype field
    ))
    casmos.add(gdspy.Label(
        text="SS",
        position=((2 * (left_most_drain[0][0]-m7_ss_extension))/2, ( left_most_drain[0][1] + right_most_drain[1][1])/2),
        anchor='s',           # southwest anchor
        layer=label_layers[layer_num['M7']][0],              # layer number
        texttype=label_layers[layer_num['M7']][1],             # NOT datatype! this is texttype field
        magnification = 1
    ))

    #Poly short
    poly_short_width_m1 = 0.21
    if poly_short_top_m1 == True:
        poly_short_top_box_m1 = gdspy.Rectangle(
            (ll[0]+ od_offset, ur[1] + poly_up_offset_m1),
            ((ll[0]+ od_offset + (nf+dummy-1)*(poly_pitch+length) + length), ur[1] + poly_up_offset_m1 + poly_short_width_m1),
            layer=layer_num['Poly'],
            datatype=layer_datatypes['Poly']['Draw'] 
        )
        casmos.add(poly_short_top_box_m1)
        
        for m, v in zip(metal_list[:-1], via_list[:-1]):
            casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[0][1] + 0.02),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1]-0.01),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            ))
            casmos = insert_via(cell=casmos, ll=poly_short_top_box_m1.get_bounding_box()[0], ur=poly_short_top_box_m1.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] +m1_strip_width - 0.01),layer=layer_num['M3'], datatype=layer_datatypes['M3']['Draw']
            ))
        casmos = insert_via(cell=casmos, ll=(poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 ), ur=(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] +m1_strip_width - 0.01),
                                layer_rules=layer_rules, via_name='V3', via_layer_num = layer_num['V3'], via_layer_datatype = layer_datatypes['V3']['Draw'], move_for_symmetry=True)
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] +2*m1_strip_width - 0.01),layer=layer_num['M4'], datatype=layer_datatypes['M4']['Draw']
            ))
        casmos = insert_via(cell=casmos, ll=(poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + m1_strip_width), ur=(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] +2 *m1_strip_width - 0.01),
                                layer_rules=layer_rules, via_name='V4', via_layer_num = layer_num['V4'], via_layer_datatype = layer_datatypes['V4']['Draw'], move_for_symmetry=True)
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + m1_strip_width),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] + 3*m1_strip_width - 0.01),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
            ))
        casmos = insert_via(cell=casmos, ll=(poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width), ur=(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] +3 *m1_strip_width - 0.01),
                                layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] + 4*m1_strip_width - 0.01),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
            ))
        casmos = insert_via(cell=casmos, ll=(poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width), ur=(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] +4*m1_strip_width - 0.01),
                                layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
        m7_top_width = 0.7
        m8_top_width = 1.04
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width + m7_top_width),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
            ))
        casmos = insert_via(cell=casmos, ll=(poly_short_top_box_m1.get_bounding_box()[0][0],poly_short_top_box_m1.get_bounding_box()[1][1] + 4*m1_strip_width - 0.01), ur=(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] + 4*m1_strip_width - 0.01 + m8_top_width / 2),
                                layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry=True)
        
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width + m8_top_width),layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw']
            ))
        casmos = insert_via(cell=casmos, ll=(poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width + m8_top_width/2), ur=(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 3*m1_strip_width + m8_top_width),
                                layer_rules=layer_rules, via_name='V8', via_layer_num = layer_num['V8'], via_layer_datatype = layer_datatypes['V8']['Draw'], move_for_symmetry=True)
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width),(poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width + 2),layer=layer_num['M9'], datatype=layer_datatypes['M9']['Draw']
            ))
        casmos.add(gdspy.Rectangle(
            (poly_short_top_box_m1.get_bounding_box()[0][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width + 1),
            (poly_short_top_box_m1.get_bounding_box()[1][0], poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width + 2),
            layer=label_layers[layer_num['M9']][0],              # layer number
            datatype=label_layers[layer_num['M9']][1]             # NOT datatype! this is texttype field
        ))
        casmos.add(gdspy.Label(
            text="GG",
            position=((poly_short_top_box_m1.get_bounding_box()[0][0] + poly_short_top_box_m1.get_bounding_box()[1][0])/2, ( poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width + 1 + poly_short_top_box_m1.get_bounding_box()[1][1] - 0.01 + 2*m1_strip_width + 3)/2),
            anchor='n',           # southwest anchor
            layer=label_layers[layer_num['M9']][0],              # layer number
            texttype=label_layers[layer_num['M9']][1],             # NOT datatype! this is texttype field
            magnification = 1
        ))
    if poly_short_bottom_m1 == True:
        poly_short_bottom_box_m1 = gdspy.Rectangle(
            (ll[0]+ od_offset, ll[1] - poly_down_offset_m1),
            ((ll[0]+ od_offset + (nf+dummy-1)*(poly_pitch+length) + length), ll[1] - poly_down_offset_m1 -  poly_short_width_m1),
            layer=layer_num['Poly'],
            datatype=layer_datatypes['Poly']['Draw'] 
        )
        casmos.add(poly_short_bottom_box_m1)
        for m, v in zip(metal_list, via_list):
            casmos = insert_via(cell=casmos, ll=poly_short_bottom_box_m1.get_bounding_box()[0], ur=poly_short_bottom_box_m1.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
            casmos.add(gdspy.Rectangle(
                (poly_short_bottom_box_m1.get_bounding_box()[0][0], poly_short_bottom_box_m1.get_bounding_box()[0][1] + 0.01),(poly_short_bottom_box_m1.get_bounding_box()[1][0], poly_short_bottom_box_m1.get_bounding_box()[1][1]-0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            ))
    #M2
    poly_short_top_m2 = True
    poly_short_bottom_m2 = True
    if poly_short_top_m2 == True:
        poly_up_offset_m2 = 0.1
    else:
        poly_up_offset_m2 = 0.14
    if poly_short_bottom_m2 == True:
        poly_down_offset_m2 = 0.1
    else:
        poly_down_offset_m2 = 0.14

    for m, v in zip(metal_list_temp, via_list_temp):
        m1_box = gdspy.Rectangle(
                (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02),(od_bottom_bbox[0][0] + m1_strip_width - 0.005, od_bottom_bbox[1][1] + 0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            )
        casmos.add(m1_box)
        m1_box = gdspy.Rectangle(
                (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02),(od_bottom_bbox[0][0] + m1_strip_width - 0.005, od_bottom_bbox[1][1] + 0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
            )
        casmos.add(m1_box)
        m1_box = gdspy.Rectangle(
                (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02),(od_bottom_bbox[0][0] + m1_strip_width - 0.005, od_bottom_bbox[1][1] + 0.02),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
            )
        casmos.add(m1_box)
        casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
        casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
        casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
        m1_box = gdspy.Rectangle(
                (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[1][1]+0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            )
        casmos.add(m1_box)
        if nf %2 == 0:
            m1_box = gdspy.Rectangle(
                    (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[1][1]+0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
                )
            casmos.add(m1_box)
            m1_box = gdspy.Rectangle(
                    (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[1][1]+0.02),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
                )
            casmos.add(m1_box)
        m1_box = gdspy.Rectangle(
                (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[1][1]+0.02),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
            )
        casmos.add(m1_box)
        casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
        if nf %2==0:
            casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                    layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
            casmos = insert_via(cell=casmos, ll=m1_box.get_bounding_box()[0], ur=m1_box.get_bounding_box()[1],
                                    layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
        m1_box = gdspy.Rectangle(
            (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation), (od_bottom_bbox[0][0] + m1_strip_width - 0.005, od_bottom_bbox[0][1]-0.02),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
        )
        casmos.add(m1_box)
        m1_box = gdspy.Rectangle(
            (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation), (od_bottom_bbox[0][0] + m1_strip_width - 0.005, od_bottom_bbox[0][1]-0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
        )
        casmos.add(m1_box)
        m1_box = gdspy.Rectangle(
            (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation), (od_bottom_bbox[0][0] + m1_strip_width - 0.005, od_bottom_bbox[0][1]-0.02),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
        )
        casmos.add(m1_box)
        m5_short_bottom_x = od_bottom_bbox[0][0] + m1_strip_width - 0.005
        ll_elongation = 1.16
        if nf % 2 == 0:
            m1_box = gdspy.Rectangle(
                (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02 - ll_elongation),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[0][1] - 0.02),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
            )
            casmos.add(m1_box)
            m1_box = gdspy.Rectangle(
                (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02 - ll_elongation),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[0][1] - 0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
            )
            casmos.add(m1_box)
            m1_box = gdspy.Rectangle(
                (od_bottom_bbox[1][0] - m1_strip_width + 0.005,od_bottom_bbox[0][1] - 0.02 - ll_elongation),(od_bottom_bbox[1][0]+0.005, od_bottom_bbox[0][1] - 0.02),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
            )
            casmos.add(m1_box)
            m5_short_bottom_x = od_bottom_bbox[1][0]+0.005
            


    for f in range(nf + dummy):
        ll = od_bottom_bbox[0]
        ur = od_bottom_bbox[1]
        poly = gdspy.Rectangle(
            (ll[0]+ od_offset + f*(poly_pitch + length) , ll[1] - poly_down_offset_m2),
            ((ll[0]+ od_offset + f*(poly_pitch + length) + length, ur[1] + poly_up_offset_m2)),
            layer=layer_num['Poly'],
            datatype=layer_datatypes['Poly']['Draw'] 
        )
        casmos.add(poly)
        poly_bbox = poly.get_bounding_box()
        if f < (nf + dummy - 1):
            for m, v in zip(metal_list_temp, via_list_temp):
                m1_box = gdspy.Rectangle(
                    (poly_bbox[1][0] + 0.02, od_bottom_bbox[0][1]- 0.02),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02, od_bottom_bbox[1][1]+0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
                )
                casmos.add(m1_box)
                casmos = insert_via(cell=casmos, ll=(poly_bbox[1][0], od_bottom_bbox[0][1]), ur=(ll[0]+ od_offset + (f+1)*(poly_pitch + length) , od_bottom_bbox[1][1]),
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
                if f%2 != 0:
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_bottom_bbox[0][1]- 0.02),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02, od_bottom_bbox[1][1]+0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
                    )
                    casmos.add(m1_box)
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_bottom_bbox[0][1]- 0.02),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02, od_bottom_bbox[1][1]+0.02),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
                    )
                    casmos.add(m1_box)
                    casmos = insert_via(cell=casmos, ll=(poly_bbox[1][0], od_bottom_bbox[0][1]), ur=(ll[0]+ od_offset + (f+1)*(poly_pitch + length) , od_bottom_bbox[1][1]),
                                    layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
                    casmos = insert_via(cell=casmos, ll=(poly_bbox[1][0], od_bottom_bbox[0][1]), ur=(ll[0]+ od_offset + (f+1)*(poly_pitch + length) , od_bottom_bbox[1][1]),
                                    layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
                if f%2 != 0:
                    ll_elongation = 1.16
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_bottom_bbox[0][1]- 0.02 - ll_elongation),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02, od_bottom_bbox[0][1]- 0.02),layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
                    )
                    casmos.add(m1_box)
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_bottom_bbox[0][1]- 0.02 - ll_elongation),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02, od_bottom_bbox[0][1]- 0.02),layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
                    )
                    casmos.add(m1_box)
                    m1_box = gdspy.Rectangle(
                        (poly_bbox[1][0] + 0.02, od_bottom_bbox[0][1]- 0.02 - ll_elongation),(ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02, od_bottom_bbox[0][1]- 0.02),layer=layer_num['M7'], datatype=layer_datatypes['M7']['Draw']
                    )
                    casmos.add(m1_box)
                    
                    if nf%2 !=0 :
                        m5_short_bottom_x = ll[0]+ od_offset + (f+1)*(poly_pitch + length) -0.02
    m5_shirt_bottom_width = 0.53
    casmos.add(gdspy.Rectangle((od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), (m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation)  , layer= layer_num['M5'], datatype = layer_datatypes['M5']['Draw']))
    casmos.add(gdspy.Rectangle((od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), (m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation)  , layer= layer_num['M6'], datatype = layer_datatypes['M6']['Draw']))
    casmos.add(gdspy.Rectangle((od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), (m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation)  , layer= layer_num['M7'], datatype = layer_datatypes['M7']['Draw']))
    
    m8_top_width += 0.2
    casmos.add(gdspy.Rectangle((od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m8_top_width), (m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation)  , layer= layer_num['M8'], datatype = layer_datatypes['M8']['Draw']))
    casmos.add(gdspy.Rectangle((od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation ), (m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation - 2)  , layer= layer_num['M9'], datatype = layer_datatypes['M9']['Draw']))
    casmos = insert_via(cell=casmos, ll=(od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), ur=(m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation), \
        layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=(od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), ur=(m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation), \
        layer_rules=layer_rules, via_name='V6', via_layer_num = layer_num['V6'], via_layer_datatype = layer_datatypes['V6']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=(od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), ur=(m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation), \
        layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=(od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation - m8_top_width), ur=(m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation - m5_shirt_bottom_width), \
        layer_rules=layer_rules, via_name='V8', via_layer_num = layer_num['V8'], via_layer_datatype = layer_datatypes['V8']['Draw'], move_for_symmetry=True)
    casmos.add(gdspy.Rectangle(
        (od_bottom_bbox[0][0]-0.005, od_bottom_bbox[0][1]-0.02 - ll_elongation-1),
        (m5_short_bottom_x, od_bottom_bbox[0][1]-0.02 - ll_elongation - 2),
        layer=label_layers[layer_num['M9']][0],              # layer number
        datatype=label_layers[layer_num['M9']][1]             # NOT datatype! this is texttype field
    ))
    casmos.add(gdspy.Label(
        text="DD",
        position=((od_bottom_bbox[0][0]-0.005 + m5_short_bottom_x)/2, ( od_bottom_bbox[0][1]-0.02 - ll_elongation - 1 + od_bottom_bbox[0][1]-0.02 - ll_elongation - 3)/2),
        anchor='s',           # southwest anchor
        layer=label_layers[layer_num['M9']][0],              # layer number
        texttype=label_layers[layer_num['M9']][1],             # NOT datatype! this is texttype field
        magnification = 1
    ))

    poly_short_width_m2 = 0.21
    if poly_short_top_m2 == True:
        poly_short_top_box_m2 = gdspy.Rectangle(
            (ll[0]+ od_offset, ur[1] + poly_up_offset_m2),
            ((ll[0]+ od_offset + (nf+dummy-1)*(poly_pitch+length) + length), ur[1] + poly_up_offset_m2 + poly_short_width_m2),
            layer=layer_num['Poly'],
            datatype=layer_datatypes['Poly']['Draw'] 
        )
        casmos.add(poly_short_top_box_m2)
        for m, v in zip(metal_list[:-1], via_list[:-1]):
            casmos = insert_via(cell=casmos, ll=poly_short_top_box_m2.get_bounding_box()[0], ur=poly_short_top_box_m2.get_bounding_box()[1],
                                    layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
            casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m2.get_bounding_box()[0][0], poly_short_top_box_m2.get_bounding_box()[0][1] + 0.02),(poly_short_top_box_m2.get_bounding_box()[1][0], poly_short_top_box_m2.get_bounding_box()[1][1]-0.01),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            ))
        casmos.add(gdspy.Rectangle(
                (poly_short_top_box_m2.get_bounding_box()[1][0], poly_short_top_box_m2.get_bounding_box()[0][1] + 0.02), (poly_short_top_box_m2.get_bounding_box()[1][0]+0.5, poly_short_top_box_m2.get_bounding_box()[1][1]-0.01),layer=layer_num['M3'], datatype=layer_datatypes['M3']['Draw']
            ))
    if poly_short_bottom_m2 == True:
        poly_short_bottom_box_m2 = gdspy.Rectangle(
            (ll[0]+ od_offset, ll[1] - poly_down_offset_m2),
            ((ll[0]+ od_offset + (nf+dummy-1)*(poly_pitch+length) + length), ll[1] - poly_down_offset_m2 -  poly_short_width_m2),
            layer=layer_num['Poly'],
            datatype=layer_datatypes['Poly']['Draw'] 
        )
        casmos.add(poly_short_bottom_box_m2)
        for m, v in zip(metal_list[:-1], via_list[:-1]):
            casmos = insert_via(cell=casmos, ll=poly_short_bottom_box_m2.get_bounding_box()[0], ur=poly_short_bottom_box_m2.get_bounding_box()[1],
                                layer_rules=layer_rules, via_name=v, via_layer_num = layer_num[v], via_layer_datatype = layer_datatypes[v]['Draw'], move_for_symmetry=True)
            casmos.add(gdspy.Rectangle(
                (poly_short_bottom_box_m2.get_bounding_box()[0][0], poly_short_bottom_box_m2.get_bounding_box()[0][1] + 0.01),(poly_short_bottom_box_m2.get_bounding_box()[1][0], poly_short_bottom_box_m2.get_bounding_box()[1][1]-0.02),layer=layer_num[m], datatype=layer_datatypes[m]['Draw']
            ))
        casmos.add(gdspy.Rectangle(
                (poly_short_bottom_box_m2.get_bounding_box()[1][0], poly_short_bottom_box_m2.get_bounding_box()[0][1] + 0.01), (poly_short_bottom_box_m2.get_bounding_box()[1][0]+0.5, poly_short_bottom_box_m2.get_bounding_box()[1][1]-0.02),layer=layer_num['M3'], datatype=layer_datatypes['M3']['Draw']
            ))
        
        casmos.add(gdspy.Rectangle(
            (poly_short_bottom_box_m2.get_bounding_box()[1][0]+0.5, poly_short_bottom_box_m2.get_bounding_box()[0][1] + 0.01), (poly_short_top_box_m2.get_bounding_box()[1][0]+1, poly_short_top_box_m2.get_bounding_box()[1][1]-0.01), layer=layer_num['M3'], datatype=layer_datatypes['M3']['Draw']
        ))
        casmos.add(gdspy.Rectangle(
            (poly_short_bottom_box_m2.get_bounding_box()[1][0]+0.5, poly_short_bottom_box_m2.get_bounding_box()[0][1] + 0.01), (poly_short_top_box_m2.get_bounding_box()[1][0]+1, poly_short_top_box_m2.get_bounding_box()[1][1]-0.01), layer=label_layers[layer_num['M3']][0], datatype=label_layers[layer_num['M3']][1]
        ))
        casmos.add(gdspy.Label(
            text="G2",
            position=((poly_short_bottom_box_m2.get_bounding_box()[1][0]+0.5 + poly_short_top_box_m2.get_bounding_box()[1][0]+1.5)/2, (poly_short_bottom_box_m2.get_bounding_box()[0][1] + 0.01 + poly_short_top_box_m2.get_bounding_box()[1][1]-0.01)/2),
            anchor='s',           # southwest anchor
            layer=label_layers[layer_num['M3']][0],              # layer number
            texttype=label_layers[layer_num['M3']][1],             # NOT datatype! this is texttype field
            magnification = 1
        ))
    #Top and bottom ACTIVE shields

    shield_offset  = 0.15
    bottom_shield_points = [(od_bottom_left_shield.get_bounding_box()[0][0] + shield_width/2, od_bottom_left_shield.get_bounding_box()[0][1] - 0.02), \
                         (od_bottom_left_shield.get_bounding_box()[0][0] + shield_width/2, poly_short_bottom_box_m2.get_bounding_box()[0][1] - 0.5 * shield_width - shield_offset), \
                            (od_bottom_right_shield.get_bounding_box()[0][0] + shield_width/2, poly_short_bottom_box_m2.get_bounding_box()[0][1] - 0.5 * shield_width - shield_offset), \
                            (od_bottom_right_shield.get_bounding_box()[0][0] + shield_width/2, od_bottom_right_shield.get_bounding_box()[0][1] - 0.02)]
    bottom_shield = gdspy.FlexPath(
        bottom_shield_points,
        shield_width,
        layer=layer_num['Active'],
        datatype=layer_datatypes['Active']['Draw'],
        ends='flush'
    )
    casmos.add(bottom_shield)
    casmos = insert_via(cell=casmos, ll=(bottom_shield_points[1][0] - shield_width/2, bottom_shield_points[1][1] - shield_width/2), ur=(bottom_shield_points[0][0] + shield_width/2, bottom_shield_points[0][1] ),
                             layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=(bottom_shield_points[2][0] -  shield_width/2, bottom_shield_points[2][1] - shield_width/2), ur=(bottom_shield_points[3][0] + shield_width/2, bottom_shield_points[3][1]),
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=(bottom_shield_points[1][0] + shield_width/2, bottom_shield_points[1][1]-shield_width/2), ur=(bottom_shield_points[2][0] - shield_width/2, bottom_shield_points[2][1]+shield_width/2),
                             layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)

    top_shield_points = [(od_top_left_shield.get_bounding_box()[0][0] + shield_width/2, od_top_left_shield.get_bounding_box()[1][1] + 0.02), \
                         (od_top_left_shield.get_bounding_box()[0][0] + shield_width/2, poly_short_top_box_m1.get_bounding_box()[1][1] + 0.5 * shield_width + shield_offset), \
                            (od_top_right_shield.get_bounding_box()[0][0] + shield_width/2, poly_short_top_box_m1.get_bounding_box()[1][1] + 0.5 * shield_width + shield_offset), \
                            (od_top_right_shield.get_bounding_box()[0][0] + shield_width/2, od_top_right_shield.get_bounding_box()[1][1] + 0.02)]
    top_shield = gdspy.FlexPath(
        top_shield_points,
        shield_width,
        layer=layer_num['Active'],
        datatype=layer_datatypes['Active']['Draw'],
        ends='flush'
    )
    casmos.add(top_shield)
    casmos = insert_via(cell=casmos, ll=(top_shield_points[0][0] - shield_width/2, top_shield_points[0][1]), ur=(top_shield_points[1][0] + shield_width/2, top_shield_points[1][1] + shield_width/2),
                             layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ur=(top_shield_points[2][0] +  shield_width/2, top_shield_points[2][1] + shield_width/2), ll=(top_shield_points[3][0] - shield_width/2, top_shield_points[3][1]),
                              layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    casmos = insert_via(cell=casmos, ll=(top_shield_points[1][0] + shield_width/2, top_shield_points[1][1]-shield_width/2), ur=(top_shield_points[2][0] - shield_width/2, top_shield_points[2][1]+shield_width/2),
                             layer_rules=layer_rules, via_name='V0', via_layer_num = layer_num['V0'], via_layer_datatype = layer_datatypes['V0']['Draw'], move_for_symmetry=True)
    #NP
    np_gap = 0.13
    np_box = gdspy.Rectangle(
        (bottom_shield_points[1][0] + np_gap + shield_width/2, bottom_shield_points[1][1] + shield_width/2),
        (top_shield_points[2][0] - np_gap - shield_width/2, top_shield_points[2][1]-shield_width/2),
        layer=layer_num['NP'],
        datatype=layer_datatypes['NP']['Draw']
    )
    casmos.add(np_box)

    #Shield M1
    m1_shield_points = [bottom_shield_points[1], bottom_shield_points[2], top_shield_points[2], top_shield_points[1],(bottom_shield_points[1][0], bottom_shield_points[1][1]-shield_width/2)]
    m1_shield_box = gdspy.FlexPath(
        m1_shield_points,
        shield_width,
        layer=layer_num['M1'],
        datatype=layer_datatypes['M1']['Draw'],
        ends='flush'
    )
    casmos.add(m1_shield_box)

    casmos.add(gdspy.Rectangle(
        (m1_shield_points[-1][0]  - shield_width/2, (m1_shield_points[-1][1] + m1_shield_points[-2][1])/2 - shield_width/2 ), (m1_shield_points[-1][0]  + shield_width/2, (m1_shield_points[-1][1] + m1_shield_points[-2][1])/2 + shield_width/2 ), layer=label_layers[layer_num['M1']][0], datatype=label_layers[layer_num['M1']][1]
    ))
    casmos.add(gdspy.Label(
        text="GND",
        position=((m1_shield_points[-1][0]  - shield_width + m1_shield_points[-1][0])/2, ((m1_shield_points[-1][1] + m1_shield_points[-2][1])/2 - shield_width/2 + (m1_shield_points[-1][1] + m1_shield_points[-2][1])/2 + shield_width/2  )/2),
        anchor='s',           # southwest anchor
        layer=label_layers[layer_num['M1']][0],              # layer number
        texttype=label_layers[layer_num['M1']][1],             # NOT datatype! this is texttype field
        magnification = 1
    ))
    #Final translation to ORIGIN (0,0)
    bbox = casmos.get_bounding_box()
    if bbox is not None:
         llx, lly = bbox[0]
         dx, dy = -llx, -lly
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    mim_cap_cell_to_export = gdspy.Cell(f'{output_gds}')
    mim_cap_cell_to_export.add(gdspy.CellReference(casmos, (dx, dy)))

    out_path = os.path.join(output_dir, f"{output_gds}.gds")
    gdspy.write_gds(out_path, cells = [mim_cap_cell_to_export, casmos])

   

def parse_args():
    parser = argparse.ArgumentParser(
        description="CASMOS layout generator"
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
        default=0.060,
        help="Gate length in micrometers (default: 0.060)"
    )

    parser.add_argument(
        "--finger_width", "-w",
        type=float,
        default=1.0,
        help="Finger width in micrometers (default: 1.0)"
    )

    parser.add_argument(
        "--number_of_fingers", "-nf",
        type=int,
        default=22,
        help="Number of fingers (default: 22)"
    )

    parser.add_argument(
        "--dummy",
        type=int,
        default=2,
        help="Number of dummy fingers (default: 2)"
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
        default="casmos",
        help="Output GDS base name without extension (default: casmos)"
    )
    parser.add_argument("--scale", "-s", type=float, default=1000.0,
                        help="Scaling factor (default: 1000)")

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 80)
    print("CASMOS GDS generator")
    print("=" * 80)
    print(f"PDK file            : {args.pdk}")
    print(f"Length (um)         : {args.length}")
    print(f"Finger width (um)   : {args.finger_width}")
    print(f"Number of fingers   : {args.number_of_fingers}")
    print(f"Dummy fingers       : {args.dummy}")
    print(f"Output directory    : {args.output_dir}")
    print(f"Output GDS name     : {args.output_gds_name}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name} --pdk /path/to/layers.json")
    print(f"  Custom  : python {script_name} --pdk /path/to/layers.json --length 0.06 --finger_width 1.2 --number_of_fingers 24 --output_dir PRIMITIVES --output_gds_name my_casmos")
    print("=" * 80)

    if not os.path.exists(args.pdk):
        raise FileNotFoundError(f"PDK file not found: {args.pdk}")

    os.makedirs(args.output_dir, exist_ok=True)

    print("\nReading PDK layer information...")
    layer_datatypes, layer_num, label_layers, layer_rules, design_info = read_pdk.readLayerInfo(args.pdk, scale=args.scale)
    print("PDK layer information loaded successfully.")

    print("\nGenerating CASMOS layout...")
    generate_casmos(
        length=args.length,
        fw=args.finger_width,
        nf=args.number_of_fingers,
        dummy=args.dummy,
        layer_datatypes=layer_datatypes,
        layer_num=layer_num,
        label_layers=label_layers,
        layer_rules=layer_rules,
        output_dir=args.output_dir,
        output_gds=args.output_gds_name
    )

    print("\nDone.")
    print(f"Generated file: {os.path.join(args.output_dir, args.output_gds_name + '.gds')}")

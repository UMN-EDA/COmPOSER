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
    via_pitch_x = layer_rules[via_name]['SpaceY'] #Special case for CAP only
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

def create_interdigitated_capacitor(
    cap_length: float =10.0,
    cap_width: float = 10.0,
    finger_width: float = 2.0,
    finger_length: float = 20.0,
    gap: float = 2.0,
    num_fingers: int = 5,
    pad_width: float = 10.0,
    pad_length: float = 5.0,
    layer: int = 1,
    datatype: int = 0,
    layer_datatypes = None,
    layer_num = None,
    label_layers = None, 
    layer_rules = None,
    output_dir = None,
    output_gds = None,
    if_cell_details = False
):

    # Create a new cell for the capacitor
    mim_cap_cell = gdspy.Cell(f"{output_gds}_dummy")
    gdspy.unit = 1e-6  # This is the default
    # Set the database grid precision to 1.0 = 1 nanometer
    gdspy.precision = 1e-9 # This is the default
    #CTM for mim cap
    ctm_rect = gdspy.Rectangle(
                    (0, 0),
                    (cap_width , cap_length),
                    layer=layer_num['CTM'],
                    datatype=layer_datatypes['CTM']['Draw']
                )
    mim_cap_cell.add(ctm_rect)

    #CBM for mim cap
    cbm_bigger_than_ctm = 1.76
    cbm_rect = gdspy.Rectangle(
                    (0-cbm_bigger_than_ctm, 0-cbm_bigger_than_ctm),
                    (cap_width+cbm_bigger_than_ctm , cap_length+cbm_bigger_than_ctm),
                    layer=layer_num['CBM'],
                    datatype=layer_datatypes['CBM']['Draw']
                )
    mim_cap_cell.add(cbm_rect)

    #M8 grid
    thickness = 1.66 #TODO
    temp_inner_box = gdspy.Rectangle(
        (-cbm_bigger_than_ctm + thickness, -cbm_bigger_than_ctm + thickness),
        (cap_width+cbm_bigger_than_ctm - thickness, cap_length+cbm_bigger_than_ctm - thickness),
        layer=0, datatype=0
    )
    # Create the band by subtracting the inner box from the outer box
    m8_outer_band = gdspy.boolean(cbm_rect, temp_inner_box, operation='not', layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])

    #M8 opening
    centre_m8_strip_thickness = 2.36
    m8_to_m8border = 0.84
    
    gap = centre_m8_strip_thickness + 2 * m8_to_m8border #TODO
    centre_line = cbm_rect.get_bounding_box()
    temp_stripe = gdspy.Rectangle((centre_line[0][0], -(gap/2)+ (centre_line[0][1]+centre_line[1][1])/2), (centre_line[1][0], +(gap/2)+ (centre_line[0][1]+centre_line[1][1])/2), layer = 0, datatype=0)
    m8_outer_band = gdspy.boolean(m8_outer_band, temp_stripe, operation='not', layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
    mim_cap_cell.add(m8_outer_band)

    #MINUS port extension
    inner_box_bbox = temp_inner_box.get_bounding_box()
    outer_m8_band_bbox = m8_outer_band.get_bounding_box()

    minus_extension_top = gdspy.Rectangle((inner_box_bbox[1][0]+thickness,inner_box_bbox[1][1]),(outer_m8_band_bbox[1][0]+m8_to_m8border + thickness, outer_m8_band_bbox[1][1]), layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
    mim_cap_cell.add(minus_extension_top)

    minus_extension_bottom = gdspy.Rectangle((inner_box_bbox[1][0]+thickness, outer_m8_band_bbox[0][1]),(outer_m8_band_bbox[1][0]+m8_to_m8border + thickness, inner_box_bbox[0][1]), layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
    mim_cap_cell.add(minus_extension_bottom)

    minus_extension_vertical = gdspy.Rectangle((inner_box_bbox[1][0]+thickness + m8_to_m8border, outer_m8_band_bbox[0][1]),(outer_m8_band_bbox[1][0]+m8_to_m8border + thickness, outer_m8_band_bbox[1][1]), layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
    mim_cap_cell.add(minus_extension_vertical)

    #Inner rail of M8
    centre_stripe = gdspy.Rectangle((centre_line[0][0]-2.5, -(centre_m8_strip_thickness/2)+ (centre_line[0][1]+centre_line[1][1])/2), (centre_line[1][0], +(centre_m8_strip_thickness/2)+ (centre_line[0][1]+centre_line[1][1])/2), layer = layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
    mim_cap_cell.add(centre_stripe)
    
    # #VIA7 for lower band of M8 (Divided into 3 polygons)
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(0-cbm_bigger_than_ctm, -cbm_bigger_than_ctm + thickness), ur=(-cbm_bigger_than_ctm + thickness,-(gap/2)+ (centre_line[0][1]+centre_line[1][1])/2),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], user_y_buffer=layer_rules['V7']['SpaceX'] - 2*layer_rules['V7']['VencA_H'])
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(0-cbm_bigger_than_ctm, 0-cbm_bigger_than_ctm), ur=(centre_line[1][0],-cbm_bigger_than_ctm + thickness),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry=True, user_x_buffer=0.0)
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(cap_width+cbm_bigger_than_ctm - thickness,-cbm_bigger_than_ctm + thickness), ur=(centre_line[1][0],-(gap/2)+ (centre_line[0][1]+centre_line[1][1])/2),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], user_y_buffer=layer_rules['V7']['SpaceX'] - 2*layer_rules['V7']['VencA_H'])
    

    # #VIA7 for upper band of M8 (Divided into 3 polygons)
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(0-cbm_bigger_than_ctm, +(gap/2)+ (centre_line[0][1]+centre_line[1][1])/2), ur=(-cbm_bigger_than_ctm + thickness,cap_length+cbm_bigger_than_ctm - thickness),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], user_y_buffer=layer_rules['V7']['SpaceX'] - 2*layer_rules['V7']['VencA_H'])
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(0-cbm_bigger_than_ctm, cap_length+cbm_bigger_than_ctm - thickness), ur=(centre_line[1][0],cap_length+cbm_bigger_than_ctm),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry=True, user_x_buffer=0.0)
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(cap_width+cbm_bigger_than_ctm - thickness,+(gap/2)+ (centre_line[0][1]+centre_line[1][1])/2), ur=(centre_line[1][0],cap_length+cbm_bigger_than_ctm - thickness),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], user_y_buffer=layer_rules['V7']['SpaceX'] - 2*layer_rules['V7']['VencA_H'])

    #M8 vertical rail start and ending points
    start_stop = temp_inner_box.get_bounding_box()

    available_x_space = start_stop[1][0] - start_stop[0][0]
    available_y_space = start_stop[1][1] - start_stop[0][1]

    #Counting the maximum number of vertical M8 rails
    inner_vertical_m8_layer_thickness = 1.74
    m8_num = (available_x_space - m8_to_m8border) // (inner_vertical_m8_layer_thickness + m8_to_m8border)
    space_for_buffer = available_x_space - m8_num * inner_vertical_m8_layer_thickness
    vertical_m8_layer_pitch = (space_for_buffer - 2 * m8_to_m8border)/(m8_num-1 +1e-10)

    ll_x = start_stop[0][0] + m8_to_m8border
    ll_y = ((centre_m8_strip_thickness/2)+ (centre_line[0][1]+centre_line[1][1])/2)
    ul_y =  ll_y + (available_y_space/2) - (centre_m8_strip_thickness/2) - m8_to_m8border
    ul_y_down = ll_y - centre_m8_strip_thickness - (available_y_space/2)  + (centre_m8_strip_thickness/2)+ m8_to_m8border
    for i in range(int(m8_num)):
        
        vert_rail_up =  gdspy.Rectangle((ll_x, ll_y),(ll_x + inner_vertical_m8_layer_thickness,ul_y), layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
        mim_cap_cell.add(vert_rail_up)
        vert_rail_down =  gdspy.Rectangle((ll_x, ll_y-centre_m8_strip_thickness),(ll_x + inner_vertical_m8_layer_thickness,ul_y_down), layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw'])
        mim_cap_cell.add(vert_rail_up)
        mim_cap_cell.add(vert_rail_down)
        # VIA7 for vertical M8 rails
        mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(ll_x, ul_y_down), ur=(ll_x + inner_vertical_m8_layer_thickness,ul_y),
                              layer_rules=layer_rules, via_name= 'V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'])
        ll_x += (vertical_m8_layer_pitch+inner_vertical_m8_layer_thickness)
    
    #M5 Shielding
    space_for_m5_shielding = cbm_rect.get_bounding_box()
    avail_x = space_for_m5_shielding[1][0] - space_for_m5_shielding[0][0]
    avail_y = space_for_m5_shielding[1][1] - space_for_m5_shielding[0][1]
    
    #Vertical and horizontal axes using M5
    m5_thickness = 1.2
    m5_pitch = 0.6

    vert_axis = gdspy.Rectangle((-m5_thickness/2+(space_for_m5_shielding[1][0] + space_for_m5_shielding[0][0])/2 , space_for_m5_shielding[0][1]), (m5_thickness/2 + (space_for_m5_shielding[1][0] + space_for_m5_shielding[0][0])/2,space_for_m5_shielding[1][1]), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
    mim_cap_cell.add(vert_axis)

    hor_axis = gdspy.Rectangle((space_for_m5_shielding[0][0], -m5_thickness/2 + (space_for_m5_shielding[1][1] + space_for_m5_shielding[0][1])/2), (space_for_m5_shielding[1][0], m5_thickness/2 + ( space_for_m5_shielding[1][1] + space_for_m5_shielding[0][1])/2), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
    mim_cap_cell.add(hor_axis)

    #Filling the 4 quadrants with M5 'L's
    num_full_L = (avail_x/2 + m5_thickness/2) // (m5_thickness+m5_pitch)
    x_coord_v = (space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 #+ m5_thickness/2
    x_coord_h = (space_for_m5_shielding[0][1] + space_for_m5_shielding[1][1])/2 #+ m5_thickness/2
    #Quadrant ++
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness)

        x_u = x_coord_v + update_factor+m5_thickness/2
        if x_u > space_for_m5_shielding[1][0]:
            x_u = space_for_m5_shielding[1][0]

        y_u = x_coord_h+update_factor
        if y_u > space_for_m5_shielding[1][1]:
            y_u = space_for_m5_shielding[1][1]

        x_l = x_coord_v + update_factor - m5_thickness/2
        y_l = space_for_m5_shielding[1][1]
        if y_u != y_l:
            vert_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(vert_rail)
        
        #Horizontal
        x_l, y_l= (x_coord_v + update_factor - m5_thickness/2, x_coord_h + update_factor - m5_thickness/2)
        x_u, y_u = space_for_m5_shielding[1][0], x_coord_h + update_factor + m5_thickness/2
        if y_l <space_for_m5_shielding[1][1] and y_u != y_l:
            if y_u > space_for_m5_shielding[1][1]:
                y_u = space_for_m5_shielding[1][1]
            hor_rail = gdspy.Rectangle(( x_l, y_l), ( x_u, y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(hor_rail)
    
    #Quadrant -+
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness)
        x_u = x_coord_v - update_factor - m5_thickness/2
        if x_u < space_for_m5_shielding[0][0]:
            x_u = space_for_m5_shielding[0][0]
        y_u = x_coord_h+update_factor
        if y_u > space_for_m5_shielding[1][1]:
            y_u = space_for_m5_shielding[1][1]
        x_l = x_coord_v - update_factor + m5_thickness/2
        y_l= space_for_m5_shielding[1][1]
        if y_l != y_u and x_l != x_u:
            vert_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(vert_rail)
        #Horizontal
        x_l, y_l= ( x_coord_v - update_factor + m5_thickness/2, x_coord_h + update_factor - m5_thickness/2)
        x_u, y_u = space_for_m5_shielding[0][0], x_coord_h + update_factor + m5_thickness/2
        if y_l <space_for_m5_shielding[1][1] and y_u != y_l:
            if y_u > space_for_m5_shielding[1][1]:
                y_u = space_for_m5_shielding[1][1]
            hor_rail = gdspy.Rectangle(( x_l, y_l), ( x_u, y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(hor_rail)

    #Quadrant --
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness)
        x_l, y_l =  x_coord_v - update_factor + m5_thickness/2, space_for_m5_shielding[0][1]
        x_u = x_coord_v - update_factor - m5_thickness/2
        if x_u < space_for_m5_shielding[0][0]:
            x_u = space_for_m5_shielding[0][0]
        y_u = x_coord_h-update_factor
        if y_u < space_for_m5_shielding[0][1]:
            y_u = space_for_m5_shielding[0][1]
        if y_u != y_l:
            vert_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(vert_rail)
        #Horizontal
        x_l, y_l = x_coord_v - update_factor + m5_thickness/2, x_coord_h - update_factor + m5_thickness/2
        x_u, y_u = space_for_m5_shielding[0][0], x_coord_h - update_factor - m5_thickness/2
        if y_l > space_for_m5_shielding[0][1] and y_u != y_l:
            if y_u < space_for_m5_shielding[0][1]:
                y_u = space_for_m5_shielding[0][1]
            hor_rail = gdspy.Rectangle(( x_l, y_l), (x_u  , y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(hor_rail)

    #Quadrant +-
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness)
        x_l, y_l =  x_coord_v + update_factor - m5_thickness/2, space_for_m5_shielding[0][1]
        x_u = x_coord_v + update_factor + m5_thickness/2
        if x_u > space_for_m5_shielding[1][0]:
            x_u = space_for_m5_shielding[1][0]

        y_u = x_coord_h-update_factor
        if y_u < space_for_m5_shielding[0][1]:
            y_u = space_for_m5_shielding[0][1]
        if y_u != y_l:
            vert_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(vert_rail)
        #Horizontal
        x_l, y_l = x_coord_v + update_factor - m5_thickness/2, x_coord_h - update_factor + m5_thickness/2
        y_u = x_coord_h - update_factor - m5_thickness/2
        x_u = space_for_m5_shielding[1][0] 
        if y_l > space_for_m5_shielding[0][1] and y_u != y_l:
            if y_u < space_for_m5_shielding[0][1]:
                y_u = space_for_m5_shielding[0][1]
            hor_rail = gdspy.Rectangle(( x_l, y_l), (x_u  , y_u), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw'])
            mim_cap_cell.add(hor_rail)

    #M5 Top and Bottom strip
    m6_terminal_strip_thickness = 0.43
    mim_cap_cell.add(gdspy.Rectangle(
        (space_for_m5_shielding[0][0], space_for_m5_shielding[1][1]-m6_terminal_strip_thickness), (space_for_m5_shielding[1]), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
    ))
    mim_cap_cell.add(gdspy.Rectangle(
        (space_for_m5_shielding[0]), (space_for_m5_shielding[1][0], space_for_m5_shielding[0][1] + m6_terminal_strip_thickness), layer=layer_num['M5'], datatype=layer_datatypes['M5']['Draw']
    ))
    mim_cap_cell.add(gdspy.Rectangle(
        ((space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 - m6_terminal_strip_thickness/2-cap_width/6, space_for_m5_shielding[1][1]-m6_terminal_strip_thickness),
        ((space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 + m6_terminal_strip_thickness/2+cap_width/6, space_for_m5_shielding[1][1]),
        layer=label_layers[layer_num['M5']][0],              # layer number
        datatype=label_layers[layer_num['M5']][1]             # NOT datatype! this is texttype field
    ))
    mim_cap_cell.add(gdspy.Label(
        text="BULK1",
        position=((space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 , ( space_for_m5_shielding[1][1] + space_for_m5_shielding[1][1])/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M5']][0],              # layer number
        texttype=label_layers[layer_num['M5']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))
    mim_cap_cell.add(gdspy.Rectangle(
        ((space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 - m6_terminal_strip_thickness/2 - cap_width/6, space_for_m5_shielding[0][1]),
        ((space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 + m6_terminal_strip_thickness/2 + cap_width/6, space_for_m5_shielding[0][1]+m6_terminal_strip_thickness),
        layer=label_layers[layer_num['M5']][0],              # layer number
        datatype=label_layers[layer_num['M5']][1]             # NOT datatype! this is texttype field
    ))
    mim_cap_cell.add(gdspy.Label(
        text="BULK2",
        position=((space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 , ( space_for_m5_shielding[0][1]+ space_for_m5_shielding[0][1] )/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M5']][0],              # layer number
        texttype=label_layers[layer_num['M5']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))


    #VIA5 Insertion between M5 and M6
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(space_for_m5_shielding[0][0], space_for_m5_shielding[1][1]-m6_terminal_strip_thickness), ur=(space_for_m5_shielding[1]),
                              layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'])

    mim_cap_cell = insert_via(cell=mim_cap_cell, ll= (space_for_m5_shielding[0]), ur=(space_for_m5_shielding[1][0], space_for_m5_shielding[0][1] + m6_terminal_strip_thickness),
                              layer_rules=layer_rules, via_name='V5', via_layer_num = layer_num['V5'], via_layer_datatype = layer_datatypes['V5']['Draw'])

    #M6 Shielding
    #Filling the 4 quadrants with M5 'L's
    num_full_L = (avail_x/2 + m5_thickness/2) // (m5_thickness+m5_pitch)
    x_coord_v = (space_for_m5_shielding[0][0] + space_for_m5_shielding[1][0])/2 #+ m5_thickness/2
    x_coord_h = (space_for_m5_shielding[0][1] + space_for_m5_shielding[1][1])/2 #+ m5_thickness/2
    #Quadrant ++
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i) * (m5_pitch +  m5_thickness) +m5_thickness/2 + m5_pitch/2
        x_l, y_l = ( x_coord_v + update_factor - m5_thickness/2, space_for_m5_shielding[1][1])
        x_u, y_u = x_coord_v + update_factor+m5_thickness/2, x_coord_h+update_factor

        if x_u > space_for_m5_shielding[1][0]:
            x_u = space_for_m5_shielding[1][0]
        if y_u > space_for_m5_shielding[1][1]:
            y_u = space_for_m5_shielding[1][1]
        if y_u  != y_l and x_u != y_u:
            vert_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(vert_rail)

        #Horizontal
        x_l, y_l = x_coord_v + update_factor - m5_thickness/2, x_coord_h + update_factor - m5_thickness/2
        x_u, y_u = space_for_m5_shielding[1][0], x_coord_h + update_factor + m5_thickness/2
        if y_l > space_for_m5_shielding[1][1]:
            y_l = space_for_m5_shielding[1][1]
        if y_u > space_for_m5_shielding[1][1]:
            y_u = space_for_m5_shielding[1][1]
        
        if x_l != x_u and y_l != y_u:
            hor_rail = gdspy.Rectangle(( x_l, y_l), ( x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(hor_rail)
    
    #Quadrant -+
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness)  - m5_pitch/2 - m5_thickness/2
        x_u, y_u = x_coord_v - update_factor + m5_thickness/2, space_for_m5_shielding[1][1]
        x_l, y_l = x_coord_v - update_factor - m5_thickness/2, x_coord_h+update_factor
        if x_u < space_for_m5_shielding[0][0]:
            x_u = space_for_m5_shielding[0][0]
        if y_l > space_for_m5_shielding[1][1]:
            y_l = space_for_m5_shielding[1][1]
        if x_l < space_for_m5_shielding[0][0]:
            x_l = space_for_m5_shielding[0][0]
        if x_l != x_u and y_l != y_u:
            vert_rail = gdspy.Rectangle(( x_l, y_l), (x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(vert_rail)
        #Horizontal
        x_u, y_u = x_coord_v - update_factor + m5_thickness/2,  x_coord_h + update_factor + m5_thickness/2
        x_l, y_l = space_for_m5_shielding[0][0], x_coord_h + update_factor - m5_thickness/2
        if y_u > space_for_m5_shielding[1][1]:
            y_u = space_for_m5_shielding[1][1]
        if y_l > space_for_m5_shielding[1][1]:
            y_l = space_for_m5_shielding[1][1]
        if x_l != x_u and y_l != y_u:
            hor_rail = gdspy.Rectangle(( x_l, y_l), (x_u , y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(hor_rail)
    
    #Quadrant --
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness) - m5_pitch/2 - m5_thickness/2
        x_l, y_l = x_coord_v - update_factor + m5_thickness/2, x_coord_h-update_factor
        x_u, y_u = x_coord_v - update_factor - m5_thickness/2, space_for_m5_shielding[0][1]
        if x_u < space_for_m5_shielding[0][0]:
            x_u = space_for_m5_shielding[0][0]
        if y_l < space_for_m5_shielding[0][1]:
            y_l = space_for_m5_shielding[0][1]
        if y_l < space_for_m5_shielding[0][1]:
            y_l = space_for_m5_shielding[0][1]
        if x_l != x_u and y_l != y_u:
            vert_rail = gdspy.Rectangle((x_l,y_l), (x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(vert_rail)
        #Horizontal
        x_u, y_u =  x_coord_v - update_factor + m5_thickness/2, x_coord_h - update_factor + m5_thickness/2
        x_l, y_l = space_for_m5_shielding[0][0], x_coord_h - update_factor - m5_thickness/2
        if y_u < space_for_m5_shielding[0][1]:
            y_u = space_for_m5_shielding[0][1]
        if y_l < space_for_m5_shielding[0][1]:
            y_l = space_for_m5_shielding[0][1]
        
        if x_l != x_u and y_l != y_u:
            hor_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(hor_rail)
    
    #Quadrant +-
    for i in range(int(num_full_L)):
        #Vertical
        update_factor = (i+1) * (m5_pitch +  m5_thickness) - m5_thickness/2 - m5_pitch/2
        x_l, y_l =  x_coord_v + update_factor - m5_thickness/2, space_for_m5_shielding[0][1]
        x_u, y_u = x_coord_v + update_factor + m5_thickness/2, x_coord_h-update_factor
        if x_u >space_for_m5_shielding[1][0]:
            x_u = space_for_m5_shielding[1][0]
        if y_u < space_for_m5_shielding[0][1]:
            y_u = space_for_m5_shielding[0][1]
        if y_l < space_for_m5_shielding[0][1]:
            y_l = space_for_m5_shielding[0][1]
        
        if x_l != x_u and y_l != y_u:
            vert_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(vert_rail)
        #Horizontal
        x_l, y_l = x_coord_v + update_factor - m5_thickness/2, x_coord_h - update_factor + m5_thickness/2
        x_u, y_u = space_for_m5_shielding[1][0], x_coord_h - update_factor - m5_thickness/2
        if y_u < space_for_m5_shielding[0][1]:
            y_u = space_for_m5_shielding[0][1]
        if y_l < space_for_m5_shielding[0][1]:
            y_l = space_for_m5_shielding[0][1]
        if x_l != x_u and y_l != y_u:
            hor_rail = gdspy.Rectangle((x_l, y_l), (x_u, y_u), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw'])
            mim_cap_cell.add(hor_rail)

    #M6 Top and Bottom strip
    m6_terminal_strip_thickness = 0.43
    mim_cap_cell.add(gdspy.Rectangle(
        (space_for_m5_shielding[0][0], space_for_m5_shielding[1][1]-m6_terminal_strip_thickness), (space_for_m5_shielding[1]), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
    ))
    mim_cap_cell.add(gdspy.Rectangle(
        (space_for_m5_shielding[0]), (space_for_m5_shielding[1][0], space_for_m5_shielding[0][1] + m6_terminal_strip_thickness), layer=layer_num['M6'], datatype=layer_datatypes['M6']['Draw']
    ))

    centre_m8_strip_bbox = centre_stripe.get_bounding_box()
    #Adding mim cap PINS
    #POSITIVE PIN
    mim_cap_cell.add(gdspy.Rectangle(
        (centre_m8_strip_bbox[0][0], centre_m8_strip_bbox[0][1]),
        (centre_m8_strip_bbox[0][0]+thickness, centre_m8_strip_bbox[0][1]+centre_m8_strip_thickness),
        layer=label_layers[layer_num['M8']][0],              # layer number
        datatype=label_layers[layer_num['M8']][1]             # NOT datatype! this is texttype field
    ))
    mim_cap_cell.add(gdspy.Label(
        text="PLUS",
        position=(centre_m8_strip_bbox[0][0], centre_m8_strip_bbox[0][1]+centre_m8_strip_thickness/2),
        layer=label_layers[layer_num['M8']][0],              # layer number
        texttype=label_layers[layer_num['M8']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))
    minus_extension_vertical_bbox = minus_extension_vertical.get_bounding_box()
    #NEGATIVE PIN
    mim_cap_cell.add(gdspy.Rectangle(
        ((minus_extension_vertical_bbox[0][0] + minus_extension_vertical_bbox[1][0])/2 - thickness/2, (minus_extension_vertical_bbox[0][1]+minus_extension_vertical_bbox[1][1])/2 - cap_width/2),
        ((minus_extension_vertical_bbox[0][0] + minus_extension_vertical_bbox[1][0])/2 + thickness/2, (minus_extension_vertical_bbox[0][1]+minus_extension_vertical_bbox[1][1])/2 + cap_width/2),
        layer=label_layers[layer_num['M8']][0],              # layer number
        datatype=label_layers[layer_num['M8']][1]             # NOT datatype! this is texttype field
    ))
    mim_cap_cell.add(gdspy.Label(
        text="MINUS",
        position=((minus_extension_vertical_bbox[0][0] + minus_extension_vertical_bbox[1][0])/2 + thickness /2, (minus_extension_vertical_bbox[0][1]+minus_extension_vertical_bbox[1][1])/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M8']][0],              # layer number
        texttype=label_layers[layer_num['M8']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))


    mim_cap_cell_bbox = mim_cap_cell.get_bounding_box()
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['CTMDMY'], datatype=layer_datatypes['CTMDMY']['Draw']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['CTMDMY'], datatype=layer_datatypes['CTMDMY']['dummy2']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy5']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy6']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy7']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy8']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy9']))


    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['RFDMY'], datatype=layer_datatypes['RFDMY']['Draw']))



    bbox = mim_cap_cell.get_bounding_box()
    if bbox is not None:
        llx, lly = bbox[0]
        dx, dy = -llx, -lly
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    mim_cap_cell_to_export = gdspy.Cell(f'{output_gds}')
    mim_cap_cell_to_export.add(gdspy.CellReference(mim_cap_cell, (dx, dy)))

    out_path = os.path.join(output_dir, f"{output_gds}.gds")
    gdspy.write_gds(out_path, cells = [mim_cap_cell_to_export, mim_cap_cell])

    if if_cell_details ==True:
        (x0, y0, x1, y1), w, h, pins = extract_cell_details(cell = mim_cap_cell, pin_order = ['PLUS', 'MINUS', 'BULK1', 'BULK2'])
        return (x0, y0, x1, y1), w, h, pins 

def create_small_mim_capacitor(
    cap_length: float =10.0,
    cap_width: float = 10.0,
    layer_datatypes = None,
    layer_num = None,
    label_layers = None, 
    layer_rules = None,
    output_dir = None,
    output_gds = None,
):
    print(f"\n\nGenerating small mim cap of size {cap_length, cap_width}")
    # Create a new cell for the capacitor
    mim_cap_cell = gdspy.Cell(f"{output_gds}_dummy")
    gdspy.unit = 1e-6  # This is the default
    # Set the database grid precision to 1.0 = 1 nanometer
    gdspy.precision = 0.005e-6 # This is the default
    #CTM for mim cap
    ctm_rect = gdspy.Rectangle(
                    (0, 0),
                    (cap_width , cap_length),
                    layer=layer_num['CTM'],
                    datatype=layer_datatypes['CTM']['Draw']
                )
    mim_cap_cell.add(ctm_rect)
    ctm_bbox = ctm_rect.get_bounding_box()
    #CBM for mim cap
    cbm_H_bigger_than_ctm = 2.4
    cbm_W_bigger_than_ctm = 0.4
    cbm_rect = gdspy.Rectangle(
                    (0-cbm_W_bigger_than_ctm, 0-cbm_H_bigger_than_ctm),
                    (cap_width+cbm_W_bigger_than_ctm , cap_length+cbm_H_bigger_than_ctm),
                    layer=layer_num['CBM'],
                    datatype=layer_datatypes['CBM']['Draw']
                )
    mim_cap_cell.add(cbm_rect)
    cbm_bbox = cbm_rect.get_bounding_box()
    #M8 grid
    top_thickness = 1.46 #TODO
    left_side_thickness = 0.84
    left_gap = 0.44
    top_gap = 0.1
    right_gap = 0.4

    #MINUS  top
    mim_cap_cell.add(gdspy.Rectangle(
        (cbm_bbox[0][0] - left_gap - left_side_thickness, cbm_bbox[1][1]-top_thickness - top_gap), (cbm_bbox[1][0] - right_gap, cbm_bbox[1][1] - top_gap), layer= layer_num['M8'], datatype=layer_datatypes['M8']['Draw']
    ))
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(cbm_bbox[0][0],cbm_bbox[1][1]-top_thickness - top_gap), ur=(cbm_bbox[1][0] - right_gap, cbm_bbox[1][1] - top_gap),
                              layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry= True)

    #MINUS bottom
    mim_cap_cell.add(gdspy.Rectangle(
        (cbm_bbox[0][0] - left_gap - left_side_thickness, cbm_bbox[0][1]+top_thickness + top_gap), (cbm_bbox[1][0] - right_gap, cbm_bbox[0][1] + top_gap), layer= layer_num['M8'], datatype=layer_datatypes['M8']['Draw']
    ))
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(cbm_bbox[0][0],cbm_bbox[0][1] + top_gap), ur=(cbm_bbox[1][0] - right_gap,cbm_bbox[0][1]+top_thickness + top_gap),
                            layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry= True)


    #MINUS Left
    left_m8 = gdspy.Rectangle(
        (cbm_bbox[0][0] - left_gap - left_side_thickness, cbm_bbox[0][1]+top_thickness + top_gap), (cbm_bbox[0][0] - left_gap,  cbm_bbox[1][1] - top_thickness - top_gap), layer= layer_num['M8'], datatype=layer_datatypes['M8']['Draw']
    )
    mim_cap_cell.add(left_m8)
    mim_cap_cell.add(gdspy.Rectangle(
        (cbm_bbox[0][0] - left_gap - left_side_thickness, cbm_bbox[0][1]+top_thickness + top_gap - top_thickness),
        (cbm_bbox[0][0] - left_gap,  cbm_bbox[1][1] - top_thickness - top_gap + top_thickness),
        layer=label_layers[layer_num['M8']][0],              # layer number
        datatype=label_layers[layer_num['M8']][1]             # NOT datatype! this is texttype field
    ))
    left_m8_box = left_m8.get_bounding_box()
    mim_cap_cell.add(gdspy.Label(
        text="MINUS",
        position=(left_m8_box[0][0], (left_m8_box[0][1] + left_m8_box[1][1])/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M8']][0],              # layer number
        texttype=label_layers[layer_num['M8']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))


    plus_right_length = 1.68
    plus_metal_thickness = 1.46
    #PLUS centre
    mid_plus = gdspy.Rectangle(
        (ctm_bbox[0][0],  (ctm_bbox[0][1] + ctm_bbox[1][1])/2 - plus_metal_thickness/2), (ctm_bbox[1][0] + plus_right_length, (ctm_bbox[0][1] + ctm_bbox[1][1])/2 + plus_metal_thickness/2), layer= layer_num['M8'], datatype=layer_datatypes['M8']['Draw']
    )
    mim_cap_cell.add(mid_plus)
    mid_plus_bbox = mid_plus.get_bounding_box()
    mim_cap_cell = insert_via(cell=mim_cap_cell, ll=mid_plus_bbox[0], ur=(mid_plus_bbox[1][0]- plus_right_length, mid_plus_bbox[1][1]),
                    layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry= True)
    plus_pin = gdspy.Rectangle(
        (cbm_bbox[1][0], mid_plus_bbox[0][1]),
        (mid_plus_bbox[1]),
        layer=label_layers[layer_num['M8']][0],              # layer number
        datatype=label_layers[layer_num['M8']][1]             # NOT datatype! this is texttype field
    )
    mim_cap_cell.add(plus_pin)
    plus_pin_box = plus_pin.get_bounding_box()
    mim_cap_cell.add(gdspy.Label(
        text="PLUS",
        position=(plus_pin_box[1][0], (plus_pin_box[0][1] + plus_pin_box[1][1])/2),
        anchor='w',           # southwest anchor
        layer=label_layers[layer_num['M8']][0],              # layer number
        texttype=label_layers[layer_num['M8']][1],             # NOT datatype! this is texttype field
        magnification = 10
    ))

    #Number of vertical rails
    pitch = layer_rules['M8']['Pitch']
    ctm_enc = 0.14
    effective_space_to_fill = ctm_bbox[1][0] - ctm_bbox[0][0] - 2 * ctm_enc
    pitch_plus_width = pitch + plus_metal_thickness
    num_rails = effective_space_to_fill // pitch_plus_width
    if (num_rails * pitch_plus_width + plus_metal_thickness) < effective_space_to_fill:
        num_rails += 1
        extra_gap = effective_space_to_fill - (num_rails-1) * pitch_plus_width - plus_metal_thickness
        pitch = pitch + extra_gap/(num_rails-1)
    else:
        extra_gap = effective_space_to_fill - (num_rails-1) * pitch_plus_width - plus_metal_thickness
        if num_rails > 1:
            pitch = pitch + extra_gap/(num_rails-1)
        else:
            pitch = pitch + extra_gap

    for i in range(int(num_rails)):
        ll_x = ctm_enc + i*(plus_metal_thickness + pitch)
        mim_cap_cell.add(gdspy.Rectangle(
            (ll_x, ctm_bbox[0][1] +ctm_enc), (ll_x + plus_metal_thickness, ctm_bbox[1][1] - ctm_enc), layer=layer_num['M8'], datatype=layer_datatypes['M8']['Draw']
        ))
        mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(ll_x, ctm_bbox[0][1] +ctm_enc), ur=(ll_x + plus_metal_thickness, mid_plus_bbox[0][1]),
                    layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry= True)
        mim_cap_cell = insert_via(cell=mim_cap_cell, ll=(ll_x, mid_plus_bbox[1][1]), ur=(ll_x + plus_metal_thickness, ctm_bbox[1][1] - ctm_enc),
                    layer_rules=layer_rules, via_name='V7', via_layer_num = layer_num['V7'], via_layer_datatype = layer_datatypes['V7']['Draw'], move_for_symmetry= True)


    mim_cap_cell_bbox = mim_cap_cell.get_bounding_box()
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['CTMDMY'], datatype=layer_datatypes['CTMDMY']['Draw']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['CTMDMY'], datatype=layer_datatypes['CTMDMY']['MIM3T']))
    mim_cap_cell.add(gdspy.Rectangle((mim_cap_cell_bbox[0]),(mim_cap_cell_bbox[1]),layer=layer_num['CTMDMY'], datatype=layer_datatypes['CTMDMY']['dummy2']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy1']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy2']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy3']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy4']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy5']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy6']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['DMEXCL'], datatype=layer_datatypes['DMEXCL']['dummy7']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['ODBLK'], datatype=layer_datatypes['ODBLK']['dummy']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['POBLK'], datatype=layer_datatypes['POBLK']['dummy']))
    mim_cap_cell.add(gdspy.Rectangle((cbm_bbox[0]),(cbm_bbox[1]),layer=layer_num['PDK'], datatype=layer_datatypes['PDK']['Draw']))
    
    bbox = mim_cap_cell.get_bounding_box()
    if bbox is not None:
        llx, lly = bbox[0]
        dx, dy = -llx, -lly
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    mim_cap_cell_to_export = gdspy.Cell(f'{output_gds}')
    mim_cap_cell_to_export.add(gdspy.CellReference(mim_cap_cell, (dx, dy)))

    out_path = os.path.join(output_dir, f"{output_gds}.gds")
    gdspy.write_gds(out_path, cells = [mim_cap_cell_to_export, mim_cap_cell])
    
    
# --- Main execution block ---
if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Shielding Ring Generator for MIMCAP")

    parser.add_argument("--len", "-l", type=float, default=10.0,
                        help="Thickness of M5 metal lines (default: 0.4)")
    parser.add_argument("--wid",  "-w", type=float, default=10.0,
                        help="Pitch between M5 lines (default: 0.6)")
    parser.add_argument("--scale", "-s", type=float, default=1000.0,
                        help="Scaling factor (default: 1000)")

    parser.add_argument("--pdk", help="Path to layers.json of the PDK")

    args = parser.parse_args()

    if not args.pdk:
        parser.error("--pdk is required. Example: python {} --pdk /path/to/layers.json".format(os.path.basename(sys.argv[0])))

    print("\n" + "=" * 80)
    print("MIM capacitor GDS generator")
    print("=" * 80)
    print(f"PDK file              : {args.pdk}")
    print(f"Cap length            : {args.len}")
    print(f"Cap width             : {args.wid}")
    print("Output directory      : current directory")
    print()
    print("Example run with default inputs:")
    print(f"python {os.path.basename(sys.argv[0])} --pdk /path/to/layers.json")
    print()
    print("This run will generate:")
    print("  1. Interdigitated capacitor  -> ./cap.gds")
    print("  2. Small MIM capacitor       -> ./small_cap.gds")
    print("=" * 80)

    print("\nReading PDK layer information...")
    layer_datatypes, layer_num, label_layers, layer_rules,design_info = read_pdk.readLayerInfo(args.pdk, scale = args.scale)
    print("PDK layer information loaded successfully.")

    print("\nGenerating interdigitated capacitor...")
    create_interdigitated_capacitor(
        cap_length=args.len,
        cap_width=args.wid,
        finger_width=2,
        finger_length=20,
        gap=2,
        num_fingers=7,
        pad_width=8,
        pad_length=10,
        layer=1,
        datatype=0,
        layer_datatypes=layer_datatypes,
        layer_num=layer_num,
        label_layers=label_layers,
        layer_rules=layer_rules,
        output_dir="examples",
        output_gds="cap"
    )
    print("Interdigitated capacitor GDS written to: ./cap.gds")

    print("\nGenerating small MIM capacitor...")
    create_small_mim_capacitor(
        cap_length=args.len,
        cap_width=args.wid,
        layer_datatypes=layer_datatypes,
        layer_num=layer_num,
        label_layers=label_layers,
        layer_rules=layer_rules,
        output_dir="examples",
        output_gds="small_cap"
    )
    print("Small MIM capacitor GDS written to: ./small_cap.gds")

    print("\nDone.")
    print("Generated files:")
    print("  examples/cap.gds")
    print("  examples/small_cap.gds")

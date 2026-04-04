import gdspy
import numpy as np
import matplotlib.pyplot as plt
import sys
from . import read_pdk
import math
import argparse
import copy
import shutil
import time
from typing import List, Tuple, Any
from pathlib import Path
import os
base = os.environ["PROJECT_HOME"]           # get the directory

#The script with generate two layouts(gds) for the specified inductor. Layout 1 is the actual gds for the complete inductor layout. Layout 2 is ALIGN friendly gds layout to use the hanan router seamlessly.


GRID = 0.005

def parse_args_old():
    parser = argparse.ArgumentParser(
        description="Generate an octagonal spiral inductor with custom parameters"
    )
    parser.add_argument(
        "--name",
        type = str,
        default = 'inductor',
        help = "GDS Name (default = inductor.gds"
    )
    parser.add_argument(
        "--type",
        type=str,
        default="std",
        help="Standard (std) os Symmetric (sym) (Default: std)"
    )
    
    parser.add_argument(
        "--num-turns", "-t",
        type=float,
        default=2.0,
        help="Total number of spiral windings. std supports quarter turn increments (e.g., 0.25, 1.50); sym accepts only whole number values. (Default: 2)."
    )
    parser.add_argument(
        "--num-sides", "-s",
        type=int,
        default=8,
        help="Number of sides of the coil. std takes ineteger, sym suports only even integer"
    )
    parser.add_argument(
        "--inner_radius", "-r",
        type=float,
        default=50.0,
        help="Inner radius in um (Starting radius)"
    )
    parser.add_argument(
        "--clearance", "-c",
        type=float,
        default=5.0,
        help="Metal?to?metal clearance in um (Gap between turns)"
    )
    parser.add_argument(
        "--width", "-w",
        type=float,
        default=5.0,
        help="Trace width in um (M9 width)"
    )
    parser.add_argument(
        "--port_extension_length", "-port_len",
        type=float,
        default=10.0,
        help="Length of the port extension in um"
    )
    parser.add_argument(
        "--shield_space_from_p2", "-shield_space",
        type=float,
        default=5.0,
        help="Shield spacing from terminals in um"
    )
    parser.add_argument(
        "--shield_metal_width", "-shield_metal_width",
        type=float,
        default=15.0,
        help="Shield metal width in um"
    )
    parser.add_argument(
        '--pgs',
        action='store_true',
        help='enable patterned ground shield'
    )
    parser.add_argument(
        '-od', '--output_dummy',
        type=Path,
        default=Path('examples/'),
        help='where to write output gds for routing'
    )
    parser.add_argument(
        '-or', '--output_real',
        type=Path,
        default=Path('examples/'),
        help='where to write gds for final layout'
    )
    parser.add_argument(
        '--gen_routing',
        action='store_true',
        help='generate extra dummy layout for routing purpose'
    )
    parser.add_argument(
        '--emx_only',
        action='store_false',
        help='Generate EMX friendly layout'
    )


    return parser.parse_args()

def robust_snap(cell_to_clean, grid_val):
    """
    Physically modifies every vertex and position in a cell 
    to be a multiple of grid_val.
    """
    # Snap all Polygons (Rectangles, FlexPaths, Polygons)
    for polygon_set in cell_to_clean.polygons:
        # A PolygonSet contains a list of vertex arrays
        snapped_list = []
        for poly in polygon_set.polygons:
            # np.round ensures 100.00000004 becomes 100.0
            snapped_poly = np.round(poly / grid_val) * grid_val
            snapped_list.append(snapped_poly)
        polygon_set.polygons = snapped_list

    # Snap all Paths (FlexPath/RobustPath)
    for path in cell_to_clean.paths:
        snapped_paths = []
        for poly in path.polygons:
            snapped_paths.append(np.round(poly / grid_val) * grid_val)
        path.polygons = snapped_paths

    # Snap all Labels
    for label in cell_to_clean.labels:
        label.position = np.round(np.array(label.position) / grid_val) * grid_val

    # Snap all References (Sub-cells)
    for ref in cell_to_clean.references:
        ref.origin = np.round(np.array(ref.origin) / grid_val) * grid_val


def regular_ngon_flexpath_old(center=(0, 0), radius=10, n_sides=8, rotation=0,
                          width=1.0, layer=1, datatype=0):
    cx, cy = center
    rot = np.deg2rad(rotation)

    # Generate vertices at equal angles
    angles = np.linspace(0, 2 * np.pi, n_sides, endpoint=False)
    points = [(cx + radius * np.cos(a + rot), cy + radius * np.sin(a + rot)) for a in angles]

    # Close path cleanly (first point back at end)
    points.append(points[0])
    points.append(points[1])

    # FlexPath with orthogonal/diagonal corner style
    return gdspy.FlexPath(points, width=width,
                          layer=layer, datatype=datatype,
                          corners="natural")  # avoids overlap gaps

def regular_ngon_flexpath(center=(0, 0), radius=10, n_sides=8, rotation=0,
                          width=1.0, layer=1, datatype=0):
    cx, cy = center
    rot = np.deg2rad(rotation)

    # 1. Generate vertices at equal angles (for both shapes)
    angles = np.linspace(0, 2 * np.pi, n_sides, endpoint=False)
    # The 'vertices' list contains the n corner points
    vertices_shield = [(cx + (radius) * np.cos(a + rot), cy + (radius) * np.sin(a + rot)) for a in angles]
    vertices_filler = [(cx + (radius + width/2) * np.cos(a + rot), cy + (radius + width/2) * np.sin(a + rot)) for a in angles]

    # --- MINIMAL CHANGE ADDITION ---
    # Create the filled polygon using the 'vertices' list.
    # We use a new layer (layer + 1) to avoid DRC issues with the path itself.
    ngon_polygon = gdspy.Polygon(vertices_filler, layer=1001, datatype=0)
    # -------------------------------
    
    # 2. Prepare points for FlexPath (original logic)
    points = vertices_shield.copy()

    # Close path cleanly (first point back at end)
    points.append(points[0])
    points.append(points[1])

    # FlexPath with orthogonal/diagonal corner style
    flex_path = gdspy.FlexPath(points, width=width,
                          layer=layer, datatype=datatype,
                          corners="natural")

    # Return both shapes in a list
    return [flex_path, ngon_polygon]

# Example of how to use this modified function:
# shapes = regular_ngon_flexpath(layer=10) # path on L=10, polygon on L=11
# cell.add(shapes)
def draw_shield_box_std(cell, spacing, shield_width, layer=0, datatype = 0, this_is_dummy = False, bbox_layer = None, bbox_datatype = None, labellayers=None, layers = None, layernames = None,
                    follow_coil_shape = False, num_sides= None):
    """
    Draw a hollow rectangular frame (strip) centered at the origin.

    Parameters
    ----------
    cell : gdspy.Cell
        The cell to add the frame to.
    spacing : float
        Half?span of the box (distance from origin to each side).
    width : float
        Trace width of the box outline.
    layer : int, optional
        GDS layer for the frame (default=0).
    """
    if follow_coil_shape == False:
        # Define the four corners (and close the loop)
        coords = [
            (-spacing, -spacing),
            ( spacing, -spacing),
            ( spacing,  spacing),
            (-spacing,  spacing),
            (-spacing, -spacing-(shield_width/2)),
        ]
        snapped_coords = snap_points(coords)
        if this_is_dummy == True:
            layer = bbox_layer
            datatype = bbox_datatype
        # Create a constant-width path around the rectangle
        frame = gdspy.FlexPath(
            snapped_coords,
            shield_width,
            layer=layer,
            datatype=datatype,
            ends='flush'
        )
        cell.add(frame)
        #Adding GND port to the shield box
        draw_label(cell = cell,
                    lower_ll = (spacing-shield_width/2,-shield_width/2) ,
                    lower_ur = (spacing + shield_width/2, shield_width/2) ,
                    upper_ll = (spacing-shield_width/2,-shield_width/2),
                    upper_ur = (spacing + shield_width/2, shield_width/2),
                    label_name="GND",
                    label_layer= labellayers[layernames['M1']][0],
                    label_datatype=labellayers[layernames['M1']][1]
                    )
        if this_is_dummy == True:
            dummy_p1_m9 = gdspy.FlexPath(((spacing,-shield_width/2), (spacing, shield_width/2)), shield_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], tolerance=0.001, precision=0.001)
            cell.add(dummy_p1_m9)
    else:
        cell.add(regular_ngon_flexpath(center=(0, 0), radius=spacing + shield_width/2, width = shield_width, n_sides=num_sides, layer=layernames['M1'], datatype = layers['M1']['Draw'], rotation = 22.5))  
        for m in ['M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9']:
            cell.add(regular_ngon_flexpath(center=(0, 0), radius=spacing + shield_width/2, width = shield_width, n_sides=num_sides, layer=layernames[m], datatype = layers[m]['Draw'], rotation = 22.5))
        draw_label(cell = cell,
                    lower_ll = (spacing + shield_width/2 - shield_width, -shield_width/2) ,
                    lower_ur = (spacing + shield_width/2, shield_width/2) ,
                    upper_ll = (spacing + shield_width/2 - shield_width, -shield_width/2),
                    upper_ur = (spacing + shield_width/2, shield_width/2),
                    label_name="GND",
                    label_layer= labellayers[layernames['M1']][0],
                    label_datatype=labellayers[layernames['M1']][1]
                    )

def extract_cell_details(
    lib,
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
    topcells = lib.top_level()
    if not topcells:
        raise ValueError("No top cell found in provided library")
    topcell = topcells[0]

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





def merge_coil_rings(
    arr: List[List[Any]],
    pairs: List[Tuple[int, int]]
) -> List[List[Any]]:
    """
    Merge each pair of subarrays in arr into one, and keep all other subarrays as they are.
    The merged subarray appears at the position of the first index in its pair.
    """
    # map first_index -> second_index for quick lookup
    merge_map = {i: j for i, j in pairs}
    used = set(i for pair in pairs for i in pair)

    result = []
    for idx, sub in enumerate(arr):
        if idx in merge_map:
            # merge only when idx is the first element of a pair
            j = merge_map[idx]
            result.append(sub + arr[j])
        elif idx in used:
            # skip any index that was merged as a second element
            continue
        else:
            # untouched subarray
            result.append(sub)

    return result

def add_to_pairs(
    pairs,
    x= None,
    y = None
):
    """
    Given a list of (x, y) tuples, add the provided x to every first element
    (if x is not None) and/or add the provided y to every second element
    (if y is not None). Return the new list of tuples.
    """
    return [
        (
            px + x if x is not None else px,
            py + y if y is not None else py
        )
        for px, py in pairs
    ]

def snap_to_grid(v, grid=GRID):
    """Round v to the nearest multiple of grid."""
    return round(v/grid) * grid

def snap_point(pt, grid=GRID):
    x, y = pt
    return (snap_to_grid(x, grid), snap_to_grid(y, grid))

def snap_points(points, grid=GRID):
    """
    Given a sequence of (x, y) tuples, return a new list
    where each coordinate is snapped to the nearest grid.
    """
    return [
        (snap_to_grid(x, grid), snap_to_grid(y, grid))
        for x, y in points
    ]

def draw_shield_box(cell, spacing,  shield_width, layer=0, datatype = 0, this_is_dummy = False, bbox_layer = None, bbox_datatype = None, labellayers=None, layers = None, layernames = None,
                    follow_coil_shape = False, num_sides= None, num_turns = None, elongation = 20, coil_width = 0, coil_spacing = 0):
    """
    Draw a hollow rectangular or polygonal frame.
    """
    
    # ---------------------------------------------------------
    # SQUARE SHIELD
    # ---------------------------------------------------------
    if follow_coil_shape == False:
        # Define the four corners (center-line of the trace)
        coords = [
            (-spacing, -spacing),
            ( spacing, -spacing),
            ( spacing,  spacing),
            (-spacing,  spacing),
            (-spacing, -spacing-(shield_width/2)), # Overlap to close the loop
        ]
        
        # Note: Assuming snap_points is defined elsewhere in your code
        snapped_coords = snap_points(coords) 
        # snapped_coords = coords 

        if this_is_dummy == True:
            layer = bbox_layer
            datatype = bbox_datatype

        frame = gdspy.FlexPath(
            snapped_coords,
            shield_width,
            layer=layer,
            datatype=datatype,
            ends='flush'
        )
        cell.add(frame)

        # Label placement (Right side wall)
        draw_label(cell = cell,
                    lower_ll = (spacing-shield_width/2,-shield_width/2) ,
                    lower_ur = (spacing + shield_width/2, shield_width/2) ,
                    upper_ll = (spacing-shield_width/2,-shield_width/2),
                    upper_ur = (spacing + shield_width/2, shield_width/2),
                    label_name="GND",
                    label_layer= labellayers[layernames['M1']][0],
                    label_datatype=labellayers[layernames['M1']][1]
                    )
        
        if this_is_dummy == True:
            dummy_p1_m9 = gdspy.FlexPath(((spacing,-shield_width/2), (spacing, shield_width/2)), shield_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], tolerance=0.001, precision=0.001)
            cell.add(dummy_p1_m9)

    # ---------------------------------------------------------
    # POLYGON SHIELD (Fixed Logic)
    # ---------------------------------------------------------
    else:
        # 1. Base Geometry Calculation
        corrected_radius = spacing / math.cos(math.pi / num_sides)
        
        # 2. Point Generation (Mutable lists)
        pts = [
            [corrected_radius * math.cos(j * (2.0 * math.pi / num_sides) - math.pi/num_sides),
             corrected_radius * math.sin(j * (2.0 * math.pi / num_sides) - math.pi/num_sides)]
            for j in range(num_sides + 1)
        ]

        # 3. APPLY THE BUFFER EXACTLY
        # This elongates the right and left vertical segments by shifting 
        # the top half of the octagon upwards.
        for p in pts[1:5]:
            p[1] += elongation
        # THE VERTICAL FLIP: Negate the Y-coordinate (p[1])
        if num_turns%2 !=0:
            for p in pts:
                p[0] = -p[0]
        pts[0]=(pts[0][0], (pts[1][1] + pts[0][1])/2 + coil_width + coil_spacing/2)
        pts.append(pts[1]) #To connect
        pts[-1]=(pts[-1][0], (pts[-1][1] + pts[-2][1])/2 - coil_width - coil_spacing/2)
        # 4. Draw the elongated Shield
        shield_poly = gdspy.FlexPath(
            pts,
            shield_width,
            layer=layernames['M1'],
            datatype=layers['M1']['Draw'],
            ends='flush'
        )
        
        cell.add(shield_poly)
        # if num_turns%2== 0:
        label_coord = (pts[4][0], (pts[4][1]+pts[5][1])/2)
        # else:
        #     label_coord = (pts[0][0], (pts[0][1]+pts[-1][1])/2)
        print(f'GND Label coord {label_coord}')
        # 5. Fixed Label (Includes all 4 required positional arguments)
        draw_label(cell = cell,
                    lower_ll = (label_coord[0]-shield_width/2, label_coord[1]-shield_width/2),
                    lower_ur = (label_coord[0]+shield_width/2, label_coord[1]+shield_width/2),
                    upper_ll = (label_coord[0]-shield_width/2, label_coord[1]-shield_width/2),
                    upper_ur = (label_coord[0]+shield_width/2, label_coord[1]+shield_width/2),
                    label_name="GND",
                    label_layer= labellayers[layernames['M1']][0],
                    label_datatype=labellayers[layernames['M1']][1]
                    )



def draw_label(cell,
             lower_ll, lower_ur,
             upper_ll, upper_ur,
             label_name, 
             label_layer=10,
             label_datatype = 0,
             lower_enc_layer=1,
             upper_enc_layer=2,
             emx_only = True):
    """
    Draw a single via cut and its metal enclosures between two metal layers.

    Parameters
    ----------
    cell : gdspy.Cell
        The GDSII cell to add the shapes to.
    lower_ll : tuple of float
        (x, y) of the lower?metal rectangle's lower?left corner.
    lower_lr : tuple of float
        (x, y) of the lower?metal rectangle's upper?right corner.
    upper_ll : tuple of float
        (x, y) of the upper?metal rectangle's lower?left corner.
    upper_lr : tuple of float
        (x, y) of the upper?metal rectangle's upper?right corner.
    via_cut_layer : int, optional
        Layer for the via cut (default=10).
    lower_enc_layer : int, optional
        Layer for the lower?metal enclosure (default=1).
    upper_enc_layer : int, optional
        Layer for the upper?metal enclosure (default=2).
    """
    # Compute the overlap box between lower and upper metal
    x_min = max(lower_ll[0], upper_ll[0])
    y_min = max(lower_ll[1], upper_ll[1])
    x_max = min(lower_ur[0], upper_ur[0])
    y_max = min(lower_ur[1], upper_ur[1])

    # 1) Draw the via cut region
    cut = gdspy.Rectangle((snap_to_grid(x_min), snap_to_grid(y_min)),
                          (snap_to_grid(x_max), snap_to_grid(y_max)),
                          layer=label_layer, datatype=label_datatype)
    cell.add(cut)
    label_pos = ((x_max+x_min)/2,(y_max+y_min)/2)
    if emx_only == True:
        if abs(x_max) > abs(x_min):
            label_pos = (x_max, (y_max+y_min)/2)
        else:
            label_pos = (x_min, (y_max+y_min)/2)
    cell.add(gdspy.Label(
        text=label_name,
        position=label_pos,
        anchor='sw',           # southwest anchor
        layer=label_layer,              # layer number
        texttype=label_datatype,             # NOT datatype! this is texttype field
        magnification = 10
    ))
    #print(f"Adding label at {label_pos} with label : {label_name} for cell : {cell}")

    # # 2) Optionally draw the lower?metal enclosure
    # lower_enc = gdspy.Rectangle(lower_ll,
    #                             lower_ur,
    #                             layer=lower_enc_layer)
    # cell.add(lower_enc)

    # # 3) Optionally draw the upper?metal enclosure
    # upper_enc = gdspy.Rectangle(upper_ll,
    #                             upper_ur,
    #                             layer=upper_enc_layer, datatype=via_cut_datatype)
    # cell.add(upper_enc)


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

def draw_via(cell, ll, ur, layer_rules, via_name, via_layer_num=0, via_layer_datatype=0,
               move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False):

    print(f"Inserting via {via_layer_num} : {via_layer_datatype} in rectangle {ll} : {ur}")

    vencA_H = layer_rules[via_name]['VencA_H'] #0.2 for VIA7
    vencP_H = layer_rules[via_name]['VencP_H'] #0.2 for VIA7
    if ignore_venc:
        vencA_H = 0
        vencP_H = 0
    via_size = layer_rules[via_name]['WidthX'] #0.36 for VIA7
    via_pitch_x = layer_rules[via_name]['SpaceX'] #0.34 for VIA7
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


def draw_via_old(cell, lm_name, lm_width, via_name, um_name, um_width, ll_x, ll_y, ur_x, ur_y, layerSpecs, layers, layerNames):

    # 1) Extract via parameters
    viaSpecs    = layerSpecs[via_name]
    via_layer   = layerNames[via_name]
    via_dtype   = layers[via_name]['Draw']
    via_size    = viaSpecs['WidthX']
    via_spacing_x = viaSpecs['SpaceX']
    via_spacing_y = viaSpecs['SpaceY']
    pitch_x       = via_size + via_spacing_x
    pitch_y       = via_size + via_spacing_y

    # 2) Compute overlap region (in case it's been clipped elsewhere)
    x_min, y_min = ll_x, ll_y
    x_max, y_max = ur_x, ur_y
    if x_max <= x_min or y_max <= y_min:
        return  # nothing to place

    # 3) Figure out how many vias fit in X and Y
    lm_dir = layerSpecs[lm_name]['Direction']
    um_dir = layerSpecs[um_name]['Direction']
    if lm_dir == 'H' and um_dir=='V':
        x_l = layerSpecs[via_name]['VencA_L']
        x_h = layerSpecs[via_name]['VencP_H']
        y_l = layerSpecs[via_name]['VencP_L']
        y_h = layerSpecs[via_name]['VencA_H']
        
    elif lm_dir == 'V' and um_dir=='H':
        x_l = layerSpecs[via_name]['VencP_L']
        x_h = layerSpecs[via_name]['VencA_H']
        y_l = layerSpecs[via_name]['VencA_L']
        y_h = layerSpecs[via_name]['VencP_H']
        

    avail_w = x_max - x_min - 2*max(x_l, x_h)
    avail_h = y_max - y_min - 2*max(y_l, y_h)
    ncols   = int(math.floor((avail_w + via_spacing_y) / pitch_y))
    nrows   = int(math.floor((avail_h + via_spacing_x) / pitch_x))
    if ncols < 1 or nrows < 1:
        ncols = nrows = 1

    # 4) Center the array in the overlap box
    used_w  = ncols * via_size + (ncols - 1) * via_spacing_x
    used_h  = nrows * via_size + (nrows - 1) * via_spacing_x
    start_x = x_min + (avail_w - used_w) / 2
    start_y = y_min + (avail_h - used_h) / 2

    # 5) Draw the grid of via cut squares
    for i in range(ncols):
        for j in range(nrows):
            x0 = start_x + i * pitch_x
            y0 = start_y + j * pitch_y
            via = gdspy.Rectangle(
                (snap_to_grid(x0),        snap_to_grid(y0)),
                (snap_to_grid(x0 + via_size), snap_to_grid(y0 + via_size)),
                layer=via_layer,
                datatype=via_dtype
            )
            cell.add(via)

def validate_internal_angles(points):
    """Validate all internal angles against TSMC 65nm rules"""
    min_angle = 80  # Minimum allowed internal angle (degrees)
    max_angle = 150 # Maximum allowed internal angle (degrees)
    
    print("\nValidating internal angles at each vertex:")
    for i in range(1, len(points)-1):
        # Get three consecutive points
        A = np.array(points[i-1])
        B = np.array(points[i])
        C = np.array(points[i+1])
        
        # Calculate vectors
        BA = A - B
        BC = C - B
        
        # Calculate internal angle at vertex B
        dot_product = np.dot(BA, BC)
        mag_BA = np.linalg.norm(BA)
        mag_BC = np.linalg.norm(BC)
        
        if mag_BA == 0 or mag_BC == 0:
            continue  # Skip zero-length segments
            
        cos_theta = dot_product / (mag_BA * mag_BC)
        cos_theta = np.clip(cos_theta, -1.0, 1.0)  # Ensure within valid range
        angle_deg = np.degrees(np.arccos(cos_theta))
        
        print(f"Vertex {i}: Internal angle = {angle_deg:.5f}°")
        
        # Check against DRC rules
        if angle_deg < min_angle:
            raise ValueError(
                f"DRC violation: Acute angle {angle_deg:.5f}° at vertex {i} "
                f"(min allowed {min_angle}°)"
            )
        elif angle_deg > max_angle:
            raise ValueError(
                f"DRC violation: Obtuse angle {angle_deg:.2f}° at vertex {i} "
                f"(max allowed {max_angle}°)"
            )
    
    print("All internal angles are within TSMC 65nm specifications!")

def generate_standard_inductor(num_turns, inner_radius, clearance, port_extension_length, width, num_sides, shield_space_from_p2, shield_metal_width, \
                               layers, layernames, labellayers, layerspecs, output_dir, draw_axes=False, pgs = False, gds_name = 'inductor', gen_routing = False, if_cell_details = False, 
                                follow_coil_shape = False):
    
    
    #Print details of the inductor
    # 1. Prepare a mapping of ?label? ? ?formatted value?
    params = {
        "Number of turns":               num_turns,
        "Inner radius (µm)":             f"{inner_radius}",
        "Clearance (µm)":                f"{clearance}",
        "Port extension length (µm)":    f"{port_extension_length}",
        "Inductor metal coil width (µm)":              f"{width}",
        "Number of sides":               num_sides,
        "Shield space from terminals (µm)":     f"{shield_space_from_p2}",
        "Shield metal width (µm)":       f"{shield_metal_width}"
    }

    # 2. Compute the box size
    key_width = max(len(k) for k in params)
    val_width = max(len(str(v)) for v in params.values())
    content_width = key_width + 2 + val_width          # two spaces between
    term_width = shutil.get_terminal_size(fallback=(content_width+4, 0)).columns
    box_width = min(content_width + 4, term_width)      # padding + borders

    # 3. Draw the box
    top    = "-" + "-" * (box_width - 2) + "-"
    title  = " Standard Inductor Configuration "
    sep    = "-" + "-" * (box_width - 2) + "-"
    bottom = "-" + "-" * (box_width - 2) + "-"

    print("\n" + top)
    print("-" + title.center(box_width - 2) + "-")
    print(sep)

    for label, value in params.items():
        line = f"{label.ljust(key_width)}  {str(value).ljust(val_width)}"
        print("- " + line.ljust(box_width - 4) + " -")

    print(bottom + "\n")


    start = time.time()
    # Create GDS structure
        # Create GDS structure
    lib = gdspy.GdsLibrary(unit=1e-6, precision=5e-9)
    cell = lib.new_cell(f"{gds_name}_fake")
    if gen_routing == True:
        dummy_lib = gdspy.GdsLibrary(unit=1e-6, precision=0.005e-6)
        dummy_cell = dummy_lib.new_cell(gds_name+"dummy")

    # Calculate the radial increment per turn to maintain constant gap
    # This is the key formula for constant clearance
    radial_inc_per_turn = (clearance + width) / math.cos(math.pi / num_sides)
    radial_step         = radial_inc_per_turn / num_sides
    # Calculate starting radius at centerline
    R0 = inner_radius + width/2.0
    angle_step = 2.0 * math.pi / num_sides
    # Generate points
    heading = math.pi/2.0
    x       = R0 * math.cos(heading)
    y       = R0 * math.sin(heading)
    points  = [(x, y)]

    
    #Initial coil coordinates geenration
    total_segs = int(num_sides * num_turns)
    for i in range(total_segs+1):
        # radius for this segment
        if num_turns > 1:
            r_i = R0 + radial_step * i
        else:
            r_i = R0
        # side length of the corresponding regular s?gon at radius r_i
        L_i = 2.0 * r_i * math.sin(math.pi / num_sides)
        # compute next vertex
        x_new = x + L_i * math.cos(heading)
        y_new = y + L_i * math.sin(heading)
        points.append((x_new, y_new))
        # turn by the exact exterior angle
        heading += angle_step
        x, y     = x_new, y_new
    xs, ys = zip(*points)
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2

    # translate all points so that bbox?center ? (0,0)
    points = [ (x - cx, y - cy) for x, y in points ]
    #Finding max_x and max_y
    max_x = max(abs(x) for (x, y) in points) + port_extension_length/2
    min_x = min(abs(x) for (x, y) in points)
    max_y = max(abs(y) for (x, y) in points) + port_extension_length/2

    #Coordinate axes for debug mode
    if draw_axes == True:
        linex = gdspy.FlexPath([(max_x, 0), (-max_x, 0)], 0.05, layer=5)
        liney = gdspy.FlexPath([(0, max_y), (0, -max_y)], 0.05, layer=5)
        cell.add(linex)
        cell.add(liney)

    #Handling the coordinates of the ports of the inductor    
    port_1_x = points[0][0]
    if num_turns % 1 == 0:
        port_1_y = clearance/2 + width/2 #(points[0][1] + points[1][1])/2
    else:
        port_1_y = 0
    if (num_turns*100)%100 == 0:
        port_2_x = points[-1][0]
        port_2_y = -clearance/2 - width/2
        
    elif (num_turns*100)%50 == 0:
        port_2_x = points[-1][0]
        port_2_y = 0
        print("Running this")
    else:
        port_2_x = 0 #- clearance #- width/2
        port_2_y = points[-1][1]

    # #Updating the coil endpoints

    points[0] = (port_1_x, port_1_y)
    points[-1] = (port_2_x, port_2_y)

    
    # #Additional coil extension for port connection (extension are w.r.t max_x, max_y)
    if (num_turns*100)%100 == 0:
        port_2_extension_length = - points[-1][0] + max_x + port_extension_length
    elif (num_turns*100)%50 == 0:
        port_2_extension_length =  points[-1][0] + max_x + port_extension_length
    else:
        if points[-1][1] < 0: 
            port_2_extension_length =  points[-1][1] + max_y + port_extension_length
        elif points[-1][1] > 0: 
            port_2_extension_length =  -points[-1][1] + max_y + port_extension_length

    port_1_extension_length = max_x - points[0][0] + port_extension_length

    if (num_turns*100)%50 == 0:
        #Port 2 extension
        if points[-1][0] < 0:
            extended_x_2 = points[-1][0] - port_2_extension_length
        else:
            extended_x_2 = points[-1][0] + port_2_extension_length
        extended_y_2 = points[-1][1] 
        points.append((extended_x_2, extended_y_2))

    else:
        #Port2 extension
        if points[-1][1]>0:
            extended_y_2 = points[-1][1] + port_2_extension_length
        else:
            extended_y_2 = points[-1][1] - port_2_extension_length
        extended_x_2 = points[-1][0] 
        points.append((extended_x_2, extended_y_2))

    #Port 1 extension (always same)
    if points[0][0] < 0:
        extended_x_1 = points[0][0] - port_1_extension_length
    else:
        extended_x_1 = points[0][0] + port_1_extension_length
    extended_y_1 = points[0][1] 
    points.insert(0, (extended_x_1, extended_y_1))

    points = [list(p) for p in points]

    # #Handling overlapping port extensions when num_turns > 1
    if num_turns > 1:
        p1_extension_end_points = copy.deepcopy(points[0:2])
        p1_extension_end_points = [list(pt) for pt in p1_extension_end_points]
        p1_extension_end_points[-1][0] = p1_extension_end_points[-1][0] - width/2
        del points[0]
        points[0][1] -= width/2 
       
        if (num_turns*100)%100 == 0:
            points[-1][0] += width
        elif (num_turns*100)%50 == 0:
            points[-1][0] -= width
        else:
            if points[-1][1] > 0:
                points[-1][1] += width
            elif points[-1][1] < 0:
                points[-1][1] -= width
        p1_extension_end_points = p1_extension_end_points[::-1] 
        mid1_1 = [p1_extension_end_points[0][0] + math.ceil(num_turns)*clearance + (math.ceil(num_turns)+1)*width,
           (p1_extension_end_points[0][1] + p1_extension_end_points[1][1]) / 2]
        p1_extension_end_points.insert(1, mid1_1)


        p1_m8_path_point = copy.deepcopy(p1_extension_end_points[:2])

        p1_m9_path_point = copy.deepcopy(p1_extension_end_points[1:])
        p1_m9_path_point[0][0] -= width
        p1_m9_path_point[-1][0] += width

        #Create M8 layer
        p1_m8 = gdspy.FlexPath(snap_points(p1_m8_path_point), width, layer=layernames['M8'], datatype=layers['M8']['Draw'], tolerance=0.001, precision=0.001)
        cell.add(p1_m8)
        p1_m9 = gdspy.FlexPath(snap_points(p1_m9_path_point), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
        cell.add(p1_m9)



        #Create vias
        #Via_M9_M8
        draw_via(cell = cell,
                 ll =( p1_extension_end_points[0][0], p1_extension_end_points[0][1]-width/2),
                 ur = ( p1_extension_end_points[0][0]+width, p1_extension_end_points[0][1]+width/2),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )

        # #Via_1_M8_M9
        draw_via(cell = cell,
                 ll =( p1_m9_path_point[0][0], p1_m9_path_point[0][1]-width/2),
                 ur = ( p1_m9_path_point[0][0]+width, p1_m9_path_point[0][1]+width/2),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )

        # #Draw port pins_P1
        draw_label(cell = cell,
                lower_ll = (p1_m9_path_point[-1][0]-width,p1_m9_path_point[0][1]-width/2) ,
                lower_ur = (p1_m9_path_point[-1][0],p1_m9_path_point[0][1]+width/2) ,
                upper_ll = (p1_m9_path_point[-1][0]-width,p1_m9_path_point[0][1]-width/2),
                upper_ur = (p1_m9_path_point[-1][0],p1_m9_path_point[0][1]+width/2),
                label_name="P1",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        if gen_routing == True:
            draw_label(cell = dummy_cell,
                    lower_ll = (p1_m9_path_point[-1][0]-width,p1_m9_path_point[0][1]-width/2) ,
                    lower_ur = (p1_m9_path_point[-1][0],p1_m9_path_point[0][1]+width/2) ,
                    upper_ll = (p1_m9_path_point[-1][0]-width,p1_m9_path_point[0][1]-width/2),
                    upper_ur = (p1_m9_path_point[-1][0],p1_m9_path_point[0][1]+width/2),
                    label_name="P1",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            dummy_p1_m9 = gdspy.FlexPath(((p1_m9_path_point[-1][0]-width,p1_m9_path_point[0][1]), (p1_m9_path_point[-1][0],p1_m9_path_point[0][1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p1_m9)
    else:
        draw_label(cell = cell,
                lower_ll = (points[0][0]-width,points[0][1]-width/2) ,
                lower_ur = (points[0][0],points[0][1]+width/2) ,
                upper_ll = (points[0][0]-width,points[0][1]-width/2),
                upper_ur = (points[0][0],points[0][1]+width/2),
                label_name="P1",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        if gen_routing == True:
            draw_label(cell = dummy_cell,
                    lower_ll = (points[0][0]-width,points[0][1]-width/2) ,
                    lower_ur = (points[0][0],points[0][1]+width/2) ,
                    upper_ll = (points[0][0]-width,points[0][1]-width/2),
                    upper_ur = (points[0][0],points[0][1]+width/2),
                    label_name="P1",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            dummy_p1_m9 = gdspy.FlexPath(((points[0][0]-width,points[0][1]), (points[0][0],points[0][1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p1_m9)
    #Draw port pins_P2
    if (num_turns*100)%100 == 0:
        l_y = points[-1][1]-width/2
        u_y = points[-1][1]+width/2
        l_x = points[-1][0]-width
        u_x = points[-1][0]
    elif (num_turns*100)%50 == 0:
        l_y = points[-1][1]-width/2
        u_y = points[-1][1]+width/2
        l_x = points[-1][0]
        u_x = points[-1][0] + width
    else:
        if points[-1][1] > 0:
            l_y = points[-1][1]-width
            u_y = points[-1][1]
        elif points[-1][1] < 0:
            l_y = points[-1][1] 
            u_y = points[-1][1] + width
        l_x = points[-1][0]-width/2
        u_x = points[-1][0]+width/2

    draw_label(cell = cell,
             lower_ll = (l_x,l_y) ,
             lower_ur = (u_x, u_y) ,
             upper_ll = (l_x,l_y),
             upper_ur = (u_x, u_y),
             label_name="P2",
             label_layer= labellayers[layernames['M9']][0],
             label_datatype=labellayers[layernames['M9']][1]
             )
    if gen_routing == True:
        draw_label(cell = dummy_cell,
                 lower_ll = (l_x,l_y) ,
                 lower_ur = (u_x, u_y) ,
                 upper_ll = (l_x,l_y),
                 upper_ur = (u_x, u_y),
                 label_name="P2",
                 label_layer= labellayers[layernames['M9']][0],
                 label_datatype=labellayers[layernames['M9']][1]
                 )
        dummy_p2_m9 = gdspy.FlexPath(((l_x,l_y+width/2), (u_x, u_y-width/2)), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
        dummy_cell.add(dummy_p2_m9)

    # #Verify angles
    # validate_internal_angles(points=points[1:-1])
    if num_turns != 1:
        spiral = gdspy.FlexPath(snap_points(points[:-1]), width, tolerance=0.001, precision=0.001, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(spiral)
        if abs((num_turns % 1 - 0.25)) < 1e-9:

            term_2_points = [points[-1], (points[-2][0], points[-2][1]- width/2)]
        elif abs((num_turns % 1 - 0.5)) < 1e-9:

            term_2_points = [points[-1], (points[-2][0]+width/2, points[-2][1])]
        elif abs((num_turns % 1 - 0.75)) < 1e-9:

            term_2_points = [points[-1], (points[-2][0], points[-2][1]+ width/2)]
        else:
   
            term_2_points = [points[-1], (points[-2][0]-width/2, points[-2][1])]
        term_2 = gdspy.FlexPath(snap_points(term_2_points), width, tolerance=0.001, precision=0.001, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(term_2)
    else:
        spiral = gdspy.FlexPath(snap_points(points[1:-1]), width, tolerance=0.001, precision=0.001, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(spiral)

        term_1_points = [points[0], (points[1][0]-width/2,points[1][1])]
        term_1 = gdspy.FlexPath(snap_points(term_1_points), width, tolerance=0.001, precision=0.001, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(term_1)

        term_2_points = [(points[-2][0]-width/2,points[-2][1]), points[-1]]
        term_2 = gdspy.FlexPath(snap_points(term_2_points), width, tolerance=0.001, precision=0.001, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(term_2)
    
    if pgs == False:

        draw_shield_box_std(cell=cell,
                        spacing= max(abs(points[-2][0]), abs(points[-2][1])) +shield_space_from_p2,
                        shield_width= shield_metal_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], labellayers = labellayers, layers = layers, layernames = layernames,
                        follow_coil_shape = follow_coil_shape, num_sides = num_sides)
        if gen_routing == True:
            
            obstacle_point = max(abs(points[-1][0]), abs(points[-1][1]))
            for l in ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9']:
                inductor_obstacle = gdspy.Rectangle((-obstacle_point+2*width, -obstacle_point+2*width), (obstacle_point-2*width, obstacle_point-2*width),layer=layernames[l], datatype=layers[l]['Draw'])        
                dummy_cell.add(inductor_obstacle)
            draw_shield_box_std(cell=dummy_cell,
                            spacing= max(abs(points[-2][0]), abs(points[-2][1]))+shield_space_from_p2,
                            shield_width= shield_metal_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], this_is_dummy = True, bbox_layer=layernames['Bbox'], bbox_datatype=layers['Bbox']['Draw'], labellayers = labellayers, layers = layers, layernames = layernames, follow_coil_shape = follow_coil_shape, num_sides = num_sides)

    else:
        generate_patterned_ground_shield(cell=cell, shield_box_spacing=max(abs(points[-2][0]), abs(points[-2][1]))+shield_space_from_p2, layerspecs=layerspecs, layer=layernames['M1'], datatype=layers['M1']['Draw'], labellayers= labellayers, layernames = layernames)
        if gen_routing == True:
            generate_patterned_ground_shield(cell=dummy_cell, shield_box_spacing=max(abs(points[-2][0]), abs(points[-2][1]))+shield_space_from_p2, layerspecs=layerspecs, layer=layernames['M1'], datatype=layers['M1']['Draw'], this_is_dummy = True, labellayers= labellayers, layernames = layernames)

    # Align to (0,0) by translating all shapes in-place
    bbox = cell.get_bounding_box()
    if bbox is not None:
        llx, lly = bbox[0]
        
        # 1. Calculate the offset
        # 2. Round the offset to the nearest multiple of the grid (5nm)
        # This prevents moving the cell by a fractional 'off-grid' amount
        dx = -round(llx / GRID) * GRID
        dy = -round(lly / GRID) * GRID
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    cell_to_export = gdspy.Cell(f'{gds_name}')
    cell_to_export.add(gdspy.CellReference(cell, (dx, dy)))

    out_path = os.path.join(output_dir, f"{gds_name}.gds")
    gdspy.write_gds(out_path, cells = [cell_to_export, cell])


    print("Shifted cell to origin. New bbox:", cell.get_bounding_box())

        
    if gen_routing == True:
        bbox = dummy_cell.get_bounding_box()         # [[x_min,y_min],[x_max,y_max]]
        if bbox is None:
            raise ValueError('Cell is empty ? nothing to shift')
        (x_min, y_min), _ = bbox

        # 3. Translate every element in?place
        for poly in dummy_cell.polygons:             # all PolygonSet objects
            poly.translate(-x_min, -y_min)
        for path in dummy_cell.paths:                # all FlexPath/RobustPath objects
            path.translate(-x_min, -y_min)
        for ref in dummy_cell.references:            # all CellReference/CellArray objects
            ref.translate(-x_min, -y_min)
        for lbl in dummy_cell.labels:                # all Label objects
            lbl.translate(-x_min, -y_min)


    # Save GDS file
    # lib.write_gds(f'{output_dir}/{gds_name}.gds')
    if gen_routing == True:
        dummy_cell.name = gds_name
        # 2) Move it in the library?s dict
        dummy_lib.cells[gds_name] = dummy_lib.cells.pop(gds_name+'dummy')
        dummy_lib.write_gds(f'{args.output_dummy}/{gds_name}.gds')
    


    elapsed = time.time() - start
    print(f"Total time taken to generate the layout with the above specifications : {elapsed:.5f} seconds")
    print(f"Layout ready to view using the command : klayout {gds_name}.gds ")
    
    if if_cell_details == True:
        (x0, y0, x1, y1), w, h, pins = extract_cell_details(lib = lib, pin_order = ['P1','P2', 'GND'])
        return (x0, y0, x1, y1), w, h, pins 


def generate_symmetric_inductor_old(num_turns, inner_radius, clearance, port_extension_length, width, num_sides, shield_space_from_p2, shield_metal_width, \
                               layers, layernames, labellayers, layerspecs, output_dir,  draw_axes=False, pgs = False, gds_name = 'inductor', gen_routing = False, if_cell_details = False, follow_coil_shape = True):
    port_extension_length = shield_space_from_p2 + shield_metal_width/2 + port_extension_length

    #Print details of the inductor
    # 1. Prepare a mapping of ?label? ? ?formatted value?
    params = {
        "Number of turns":               num_turns,
        "Inner radius (µm)":             f"{inner_radius}",
        "Clearance (µm)":                f"{clearance}",
        "Port extension length (µm)":    f"{port_extension_length}",
        "Inductor metal coil width (µm)":              f"{width}",
        "Number of sides":               num_sides,
        "Shield space from terminals (µm)":     f"{shield_space_from_p2}",
        "Shield metal width (µm)":       f"{shield_metal_width}"
    }
    
    # 2. Compute the box size
    key_width = max(len(k) for k in params)
    val_width = max(len(str(v)) for v in params.values())
    content_width = key_width + 2 + val_width          # two spaces between
    term_width = shutil.get_terminal_size(fallback=(content_width+4, 0)).columns
    box_width = min(content_width + 4, term_width)      # padding + borders

    # 3. Draw the box
    top    = "-" + "-" * (box_width - 2) + "-"
    title  = " Symmetric Inductor Configuration "
    sep    = "-" + "-" * (box_width - 2) + "-"
    bottom = "-" + "-" * (box_width - 2) + "-"

    print("\n" + top)
    print("-" + title.center(box_width - 2) + "-")
    print(sep)

    for label, value in params.items():
        line = f"{label.ljust(key_width)}  {str(value).ljust(val_width)}"
        print("- " + line.ljust(box_width - 4) + " -")

    print(bottom + "\n")


    start = time.time()
    # Create GDS structure
        # Create GDS structure
    lib = gdspy.GdsLibrary(unit=1e-9, precision=5e-9)
    cell = lib.new_cell(f"{gds_name}_fake")
    if gen_routing == True:
        dummy_lib = gdspy.GdsLibrary(unit=1e-6, precision=5e-9)
        dummy_cell = dummy_lib.new_cell(gds_name+"dummy")

    radial_step = (clearance + width) / math.cos(math.pi / num_sides)
    angle_step = 2.0 * math.pi / num_sides

    # centerline radii for each ring
    radii = [
        inner_radius  + n * radial_step
        for n in range(int(num_turns))
    ]

    rotation = -math.pi/num_sides
    rings = []
    for ri, r in enumerate(radii):

        for i in range(int(num_sides)):
            pts = [
                (r * math.cos(i * angle_step + rotation),
                r * math.sin(i * angle_step + rotation))
                for i in range(num_sides + 1)  # +1 to close the ring
            ]
        start1 = copy.deepcopy(pts[0])
        start2 = copy.deepcopy(pts[1])
        if ri == 0:
            temp_clearance_s = 0 
            temp_clearance_e = clearance + width
        else:
            temp_clearance_s = clearance + width
            temp_clearance_e = clearance + width
        
        

        mid_s1 = ((start1[0] + start2[0])/2,((start1[1] + start2[1])/2)+ temp_clearance_s/2) 
        mid_s2 = ((start1[0] + start2[0])/2,((start1[1] + start2[1])/2)- temp_clearance_s/2) 

        end1 = copy.deepcopy(pts[int(num_sides/2)])
        end2 = copy.deepcopy(pts[int(num_sides/2)+1])
        mid_e1 = ((end1[0] + end2[0])/2,((end1[1] + end2[1])/2)+ temp_clearance_e/2) 
        mid_e2 = ((end1[0] + end2[0])/2,((end1[1] + end2[1])/2)- temp_clearance_e/2) 

        pts1 = copy.deepcopy(pts[:int(num_sides/2)+1])
        pts2 = copy.deepcopy(pts[int(num_sides/2):])

        # pts1 = add_to_pairs(pairs=pts1, y=width)
        # pts2 = add_to_pairs(pairs=pts2, y=-width)

        pts1[0] = mid_s1
        pts1.append(mid_e1)
        
        pts2[0] = mid_e2
        pts2.append(mid_s2)
        

        rings.append(pts1)
        rings.append(pts2)
        
    new_rings = rings
    #M9 Joints
    for i in range(0, int(num_turns-1), 2):
        new_rings = merge_coil_rings(arr=new_rings, pairs=[(0,i+3)])
        if i < num_turns-2:
            new_rings = merge_coil_rings(arr=new_rings, pairs=[(0,i+3)])


    #M8 Joints
    for i in range(len(new_rings[1:-1])):
        if i%2 == 0:
            extension_1 = (new_rings[i+1][0][0], new_rings[i+1][0][1]-width) 
            extension_2 = (new_rings[i+2][-1][0], new_rings[i+2][-1][1]+width) 
        else:
            extension_1 = (new_rings[i+1][0][0], new_rings[i+1][0][1]+width)
            extension_2 = (new_rings[i+2][-1][0], new_rings[i+2][-1][1]-width)
        
        #Handling the case when via falls out of M9 for small radius
        point1 = copy.deepcopy(new_rings[i+1][0])
        point2 = copy.deepcopy(new_rings[i+2][-1])
        print(point1, point2)
        m8_joint_points = [extension_1, point1, point2, extension_2]
        
        cell.add(gdspy.FlexPath(snap_points(m8_joint_points), width, layer=layernames['M8'], datatype=layers['M8']['Draw']))
        #Left
        if i%2 == 0:
            draw_via(cell = cell,
                 ll =( extension_1[0]-width/2, extension_1[1]),
                 ur = ( extension_1[0]+width/2, extension_1[1]+width),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
            draw_via(cell = cell,
                 ll =( extension_2[0]-width/2, extension_2[1]-width),
                 ur = ( extension_2[0]+width/2, extension_2[1]),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )

        #Right
        else:
            draw_via(cell = cell,
                 ll =(  extension_1[0]-width/2, extension_1[1]-width),
                 ur = ( extension_1[0]+width/2, extension_1[1]),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
            draw_via(cell = cell,
                 ll =( extension_2[0]-width/2, extension_2[1]),
                 ur = ( extension_2[0]+width/2, extension_2[1]+width),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
          

    
    #Port extension
    port_extension_length = port_extension_length + width/2
    p1 = copy.deepcopy(new_rings[0][-1])
    p2 = copy.deepcopy(new_rings[-1][0])
    if num_turns%2 == 0:
        p1_extension = p1[0] + port_extension_length
        p2_extension = p2[0] + port_extension_length
        new_rings[0].append((p1_extension, p1[1]))
        new_rings[-1].insert(0, (p2_extension, p2[1]))
    else:
        p1_extension = p1[0] - port_extension_length
        p2_extension = p2[0] - port_extension_length
        new_rings[0].append((p1_extension, p1[1]))
        new_rings[-1].insert(0, (p2_extension, p2[1]))    

    if num_turns%2 == 0:
        draw_label(cell = cell,
                lower_ll = (p1_extension, p1[1]+width/2) ,
                lower_ur = (p1_extension - width, p1[1]-width/2),
                upper_ll = (p1_extension, p1[1]+width/2),
                upper_ur = (p1_extension - width, p1[1]-width/2),
                label_name="P1",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        draw_label(cell = cell,
                lower_ll = (p2_extension, p2[1]+width/2) ,
                lower_ur = (p2_extension - width, p2[1]-width/2),
                upper_ll = (p2_extension, p2[1]+width/2),
                upper_ur = (p2_extension - width, p2[1]-width/2),
                label_name="P2",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        if gen_routing == True:
            draw_label(cell = dummy_cell,
                    lower_ll = (p1_extension, p1[1]+width/2) ,
                    lower_ur = (p1_extension - width, p1[1]-width/2),
                    upper_ll = (p1_extension, p1[1]+width/2),
                    upper_ur = (p1_extension - width, p1[1]-width/2),
                    label_name="P1",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            draw_label(cell = dummy_cell,
                    lower_ll = (p2_extension, p2[1]+width/2) ,
                    lower_ur = (p2_extension - width, p2[1]-width/2),
                    upper_ll = (p2_extension, p2[1]+width/2),
                    upper_ur = (p2_extension - width, p2[1]-width/2),
                    label_name="P2",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            dummy_p1_m9 = gdspy.FlexPath(((p1_extension, p1[1]), (p1_extension - width, p1[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p1_m9)
            dummy_p2_m9 = gdspy.FlexPath(((p2_extension, p2[1]), (p2_extension - width, p2[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p2_m9)
    else:
        draw_label(cell = cell,
                lower_ll = (p1_extension, p1[1]+width/2) ,
                lower_ur = (p1_extension + width, p1[1]-width/2),
                upper_ll = (p1_extension, p1[1]+width/2),
                upper_ur = (p1_extension + width, p1[1]-width/2),
                label_name="P1",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        draw_label(cell = cell,
                lower_ll = (p2_extension, p2[1]+width/2) ,
                lower_ur = (p2_extension + width, p2[1]-width/2),
                upper_ll = (p2_extension, p2[1]+width/2),
                label_name="P2",
                upper_ur = (p2_extension + width, p2[1]-width/2),
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        if gen_routing == True:
            draw_label(cell = dummy_cell,
                    lower_ll = (p1_extension, p1[1]+width/2) ,
                    lower_ur = (p1_extension + width, p1[1]-width/2),
                    upper_ll = (p1_extension, p1[1]+width/2),
                    upper_ur = (p1_extension + width, p1[1]-width/2),
                    label_name="P1",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            draw_label(cell = dummy_cell,
                    lower_ll = (p2_extension, p2[1]+width/2) ,
                    lower_ur = (p2_extension + width, p2[1]-width/2),
                    upper_ll = (p2_extension, p2[1]+width/2),
                    label_name="P2",
                    upper_ur = (p2_extension + width, p2[1]-width/2),
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            dummy_p1_m9 = gdspy.FlexPath(((p1_extension, p1[1]), (p1_extension + width, p1[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p1_m9)
            dummy_p2_m9 = gdspy.FlexPath(((p2_extension, p2[1]), (p2_extension + width, p2[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p2_m9)
    #symmetric
    if pgs == False:
        draw_shield_box(cell=cell,
                        spacing= max(abs(p2[0]),abs(p1[0]))+shield_space_from_p2 ,
                        shield_width= shield_metal_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], labellayers = labellayers, layers = layers, layernames = layernames,
                        follow_coil_shape = follow_coil_shape, num_sides = num_sides)
        if gen_routing == True:
            obstacle_point = max(abs(p2[0]),abs(p1[0]))
            for l in ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9']:
                inductor_obstacle = gdspy.Rectangle((-obstacle_point+2*width, -obstacle_point+2*width), (obstacle_point-2*width, obstacle_point-2*width),layer=layernames[l], datatype=layers[l]['Draw'])        
                dummy_cell.add(inductor_obstacle)
            draw_shield_box(cell=dummy_cell,
                            spacing= max(abs(p2_extension),abs(p1_extension))+shield_space_from_p2 ,
                            shield_width= shield_metal_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], this_is_dummy = True, bbox_layer=layernames['Bbox'], bbox_datatype=layers['Bbox']['Draw'], labellayers = labellayers, layers = layers, layernames = layernames)
        

    else:
        generate_patterned_ground_shield(cell=cell, shield_box_spacing=max(abs(p2_extension),abs(p1_extension))+shield_space_from_p2,  layerspecs=layerspecs, layer=layernames['M1'], datatype=layers['M1']['Draw'], labellayers= labellayers, layernames = layernames)
        if gen_routing == True:
            generate_patterned_ground_shield(cell=dummy_cell, shield_box_spacing=max(abs(p2_extension),abs(p1_extension))+shield_space_from_p2,  layerspecs=layerspecs, layer=layernames['M1'], datatype=layers['M1']['Draw'], this_is_dummy = True, labellayers= labellayers, layernames = layernames)
    
    for ring in new_rings:
        spiral = gdspy.FlexPath(snap_points(ring), width, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(spiral)
    # Save GDS file
        bbox = cell.get_bounding_box()         # [[x_min,y_min],[x_max,y_max]]
    if bbox is None:
        raise ValueError('Cell is empty ? nothing to shift')
    (x_min, y_min), _ = bbox



    robust_snap(cell, GRID)

    # Align to (0,0) by translating all shapes in-place
    bbox = cell.get_bounding_box()
    if bbox is not None:
        llx, lly = bbox[0]
        dx, dy = -llx, -lly
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    cell_to_export = gdspy.Cell(f'{gds_name}')
    cell_to_export.add(gdspy.CellReference(cell, (dx, dy)))

    out_path = os.path.join(output_dir, f"{gds_name}.gds")
    gdspy.write_gds(out_path, cells = [cell_to_export, cell])


        
    if gen_routing == True:
        bbox = dummy_cell.get_bounding_box()         # [[x_min,y_min],[x_max,y_max]]
        if bbox is None:
            raise ValueError('Cell is empty ? nothing to shift')
        (x_min, y_min), _ = bbox

        # 3. Translate every element in?place
        for poly in dummy_cell.polygons:             # all PolygonSet objects
            poly.translate(-x_min, -y_min)
        for path in dummy_cell.paths:                # all FlexPath/RobustPath objects
            path.translate(-x_min, -y_min)
        for ref in dummy_cell.references:            # all CellReference/CellArray objects
            ref.translate(-x_min, -y_min)
        for lbl in dummy_cell.labels:                # all Label objects
            lbl.translate(-x_min, -y_min)


    # Save GDS file
    # lib.write_gds(f'{output_dir}/{gds_name}.gds')
    if gen_routing == True:
        dummy_cell.name = gds_name
        # 2) Move it in the library?s dict
        dummy_lib.cells[gds_name] = dummy_lib.cells.pop(gds_name+'dummy')
        dummy_lib.write_gds(f'{args.output_dummy}/{gds_name}.gds')
    


    elapsed = time.time() - start
    print(f"Total time taken to generate the layout with the above specifications : {elapsed:.5f} seconds")
    print(f"Layout ready to view using the command : klayout {gds_name}.gds ")
    
    if if_cell_details == True:
        (x0, y0, x1, y1), w, h, pins = extract_cell_details(lib = lib, pin_order = ['P1','P2', 'GND'])
        return (x0, y0, x1, y1), w, h, pins 

def generate_symmetric_inductor(num_turns, inner_radius, clearance, port_extension_length, width, num_sides, shield_space_from_p2, shield_metal_width, \
                               layers, layernames, labellayers, layerspecs, output_dir,  draw_axes=True, pgs = False, gds_name = 'inductor', gen_routing = False, if_cell_details = False, follow_coil_shape = True):
    port_extension_length = shield_space_from_p2 + shield_metal_width/2 + port_extension_length

    #Print details of the inductor
    # 1. Prepare a mapping of ?label? ? ?formatted value?
    params = {
        "Number of turns":               num_turns,
        "Inner radius (µm)":             f"{inner_radius}",
        "Clearance (µm)":                f"{clearance}",
        "Port extension length (µm)":    f"{port_extension_length}",
        "Inductor metal coil width (µm)":              f"{width}",
        "Number of sides":               num_sides,
        "Shield space from terminals (µm)":     f"{shield_space_from_p2}",
        "Shield metal width (µm)":       f"{shield_metal_width}"
    }
    
    # 2. Compute the box size
    key_width = max(len(k) for k in params)
    val_width = max(len(str(v)) for v in params.values())
    content_width = key_width + 2 + val_width          # two spaces between
    term_width = shutil.get_terminal_size(fallback=(content_width+4, 0)).columns
    box_width = min(content_width + 4, term_width)      # padding + borders

    # 3. Draw the box
    top    = "-" + "-" * (box_width - 2) + "-"
    title  = " Symmetric Inductor Configuration "
    sep    = "-" + "-" * (box_width - 2) + "-"
    bottom = "-" + "-" * (box_width - 2) + "-"

    print("\n" + top)
    print("-" + title.center(box_width - 2) + "-")
    print(sep)

    for label, value in params.items():
        line = f"{label.ljust(key_width)}  {str(value).ljust(val_width)}"
        print("- " + line.ljust(box_width - 4) + " -")

    print(bottom + "\n")


    start = time.time()
    # Create GDS structure
        # Create GDS structure
    lib = gdspy.GdsLibrary(unit=1e-9, precision=5e-9)
    cell = lib.new_cell(f"{gds_name}_fake")
    if gen_routing == True:
        dummy_lib = gdspy.GdsLibrary(unit=1e-6, precision=5e-9)
        dummy_cell = dummy_lib.new_cell(gds_name+"dummy")

    radial_step = (clearance + width) / math.cos(math.pi / num_sides)
    angle_step = 2.0 * math.pi / num_sides

    # centerline radii for each ring
    r0 = (inner_radius + width/2.0) / math.cos(math.pi / num_sides)

    radii = [
        r0 + n * radial_step
        for n in range(int(num_turns))
    ]
    elongation = 20
    rotation = -math.pi/num_sides
    rings = []
    for ri, r in enumerate(radii):

        for i in range(int(num_sides)):
            pts = [
                [r * math.cos(j * angle_step + rotation),
                r * math.sin(j * angle_step + rotation)]
                for j in range(num_sides + 1)  # +1 to close the ring
            ]
            for p in pts[1:5]:
                p[1] += elongation
        #For cewnter taps
        if ri == 0:
            centre_tap_width = layerspecs["M7"]["WidthMax"]
            centre_tap_points = [(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2), (pts[0][0] + centre_tap_width/2 + (num_turns-1)*(clearance+width)+port_extension_length, (pts[0][1]+pts[1][1])/2)]
            
            if num_turns == 1:  #For single turn inductor using M9, no need of vias
                centre_tap = gdspy.Rectangle((pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),(pts[0][0] + width/2 + (num_turns-1)*(clearance+width)+port_extension_length , (pts[0][1]+pts[1][1])/2 + centre_tap_width/2), layer=layernames['M9'], datatype=layers['M9']['Draw'])
                
                draw_label(cell = cell,
                    lower_ll = (pts[0][0] + (num_turns-1)*(clearance+width)+port_extension_length -centre_tap_width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2) ,
                    lower_ur = (pts[0][0] + width/2 + (num_turns-1)*(clearance+width)+port_extension_length , (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                    upper_ll = (pts[0][0] + (num_turns-1)*(clearance+width)+port_extension_length -centre_tap_width/2, (pts[0][1]+pts[1][1])/2 - width/2),
                    upper_ur = (pts[0][0] + width/2 + (num_turns-1)*(clearance+width)+port_extension_length , (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                    label_name="CT",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            elif num_turns % 2!=0: #For odd number of turns of the inductor, on M7, need M8 in between with VIA stacks
                centre_tap = gdspy.FlexPath(snap_points(centre_tap_points), centre_tap_width, layer=layernames['M7'], datatype=layers['M7']['Draw'])
                cell.add(gdspy.FlexPath(snap_points([(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2),(pts[0][0] + width/2, (pts[0][1]+pts[1][1])/2)]), centre_tap_width, layer=layernames['M8'], datatype=layers['M8']['Draw']))
                draw_via(cell = cell,
                 ll =(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),
                 ur = (pts[0][0] + width/2, (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                 layer_rules = layerspecs,
                 via_name = 'V7',
                 via_layer_num = layernames['V7'],
                 via_layer_datatype=layers['V7']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
                draw_via(cell = cell,
                 ll =(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),
                 ur = (pts[0][0] + width/2, (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
                draw_label(cell = cell,
                    lower_ll = (pts[0][0] + (num_turns-1)*(clearance+width)+port_extension_length -centre_tap_width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2) ,
                    lower_ur = (pts[0][0] + centre_tap_width/2 + (num_turns-1)*(clearance+width)+port_extension_length , (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                    upper_ll = (pts[0][0] + (num_turns-1)*(clearance+width)+port_extension_length -centre_tap_width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),
                    upper_ur = (pts[0][0] + centre_tap_width/2 + (num_turns-1)*(clearance+width)+port_extension_length , (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                    label_name="CT",
                    label_layer= labellayers[layernames['M7']][0],
                    label_datatype=labellayers[layernames['M7']][1]
                    )
            else:
                centre_tap = gdspy.FlexPath(snap_points(centre_tap_points), centre_tap_width, layer=layernames['M7'], datatype=layers['M7']['Draw'])
                cell.add(gdspy.FlexPath(snap_points([(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2),(pts[0][0] + width/2, (pts[0][1]+pts[1][1])/2 )]), centre_tap_width, layer=layernames['M8'], datatype=layers['M8']['Draw']))
                draw_label(cell = cell,
                    lower_ll = (pts[0][0] + (num_turns-1)*(clearance+width)+port_extension_length - centre_tap_width/2 , (pts[0][1]+pts[1][1])/2 - centre_tap_width/2) ,
                    lower_ur = (pts[0][0]  + (num_turns-1)*(clearance+width)+port_extension_length + centre_tap_width/2, (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                    upper_ll = (pts[0][0] + (num_turns-1)*(clearance+width)+port_extension_length - centre_tap_width/2 , (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),
                    upper_ur = (pts[0][0]  + (num_turns-1)*(clearance+width)+port_extension_length + centre_tap_width/2, (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                    label_name="CT",
                    label_layer= labellayers[layernames['M7']][0],
                    label_datatype=labellayers[layernames['M7']][1]
                    )
                draw_via(cell = cell,
                 ll =(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),
                 ur = (pts[0][0] + width/2, (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                 layer_rules = layerspecs,
                 via_name = 'V7',
                 via_layer_num = layernames['V7'],
                 via_layer_datatype=layers['V7']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
                draw_via(cell = cell,
                 ll =(pts[0][0] - width/2, (pts[0][1]+pts[1][1])/2 - centre_tap_width/2),
                 ur = (pts[0][0] + width/2, (pts[0][1]+pts[1][1])/2 + centre_tap_width/2),
                 layer_rules = layerspecs,
                 via_name = 'V8',
                 via_layer_num = layernames['V8'],
                 via_layer_datatype=layers['V8']['Draw'], 
                 move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                 )
               
            cell.add(centre_tap)
        start1 = copy.deepcopy(pts[0])
        start2 = copy.deepcopy(pts[1])
        if ri == 0:
            temp_clearance_s = 0 
            temp_clearance_e = clearance + width
        else:
            temp_clearance_s = clearance + width
            temp_clearance_e = clearance + width
        mid_s1 = ((start1[0] + start2[0])/2,((start1[1] + start2[1])/2)+ temp_clearance_s/2) 
        mid_s2 = ((start1[0] + start2[0])/2,((start1[1] + start2[1])/2)- temp_clearance_s/2) 
        # print(f"Mids: ", mid_s1, mid_s2)
        end1 = copy.deepcopy(pts[int(num_sides/2)])
        end2 = copy.deepcopy(pts[int(num_sides/2)+1])
        mid_e1 = ((end1[0] + end2[0])/2,((end1[1] + end2[1])/2)+ temp_clearance_e/2) 
        mid_e2 = ((end1[0] + end2[0])/2,((end1[1] + end2[1])/2)- temp_clearance_e/2) 
        pts1 = copy.deepcopy(pts[:int(num_sides/2)+1])
        pts2 = copy.deepcopy(pts[int(num_sides/2):])
        if ri%2 ==0 :
            if ri!=0:
                mid_s1 = (mid_s1[0], mid_s1[1]+width/2)
            if ri != len(radii)-1:
                mid_e2 = (mid_e2[0], mid_e2[1]-width/2)
            
        if ri%2 !=0:
            mid_e1 = (mid_e1[0], mid_e1[1]+width/2)
            if ri != len(radii)-1:
                mid_s2 = (mid_s2[0], mid_s2[1]-width/2)
                
        pts1[0] = mid_s1
        pts1.append(mid_e1)
        pts2[0] = mid_e2
        pts2.append(mid_s2)
        rings.append(pts1)
        rings.append(pts2)
    
    new_rings = rings
    print(f"New rings : {new_rings}")
    i = 0
    while True:
        print(f"Check i {i}")
        if i + 3> num_turns*2:
            print(f"Stopping: need i+3 but len(new_rings)={len(new_rings)}")
            break 
        if rings[i][-1][1] + width > rings[i][-2][1]:
            upper_extension_factor =  rings[i][-2][1]  
        else:
            upper_extension_factor = width + rings[i][-1][1]
        if rings[i+3][0][1] - width < rings[i+3][1][1]:
            lower_extension_factor = rings[i+3][1][1]
        else:
            lower_extension_factor = rings[i+3][0][1]- width
        cell.add(gdspy.FlexPath(snap_points([(rings[i][-1][0], upper_extension_factor), rings[i][-1],  rings[i+3][0], (rings[i+3][0][0],lower_extension_factor)]), width, layer=layernames['M9'], datatype=layers['M9']['Draw']))


        if num_turns %2 == 0:
            if i + 5 <= num_turns*2:
                if rings[i+2][0][1]+width > rings[i+2][1][1]:
                    upper_extension_factor =  rings[i+2][1][1]
                else:
                    upper_extension_factor = width + rings[i+2][0][1]
                if  rings[i+5][-1][1]-width <  rings[i+5][-2][1]:
                    lower_extension_factor =  rings[i+5][-2][1]
                else:
                    lower_extension_factor =  rings[i+5][-1][1]-width
                cell.add(gdspy.FlexPath(snap_points([(rings[i+2][0][0], upper_extension_factor), rings[i+2][0], rings[i+5][-1], (rings[i+5][-1][0], lower_extension_factor)]), width, layer=layernames['M9'], datatype=layers['M9']['Draw']))
        else:
            if rings[i+2][0][1]+width > rings[i+2][1][1]:
                upper_extension_factor =  rings[i+2][1][1]
            else:
                upper_extension_factor = width + rings[i+2][0][1]
            if  rings[i+5][-1][1]-width <  rings[i+5][-2][1]:
                lower_extension_factor =  rings[i+5][-2][1]
            else:
                lower_extension_factor =  rings[i+5][-1][1]-width
            cell.add(gdspy.FlexPath(snap_points([(rings[i+2][0][0], upper_extension_factor), rings[i+2][0], rings[i+5][-1], (rings[i+5][-1][0], lower_extension_factor)]), width, layer=layernames['M9'], datatype=layers['M9']['Draw']))
        i += 4
        
    #M8 Joints
    print(f"Running for {len(new_rings)}")
    for i in range(0, len(new_rings)-2, 2):
        if i%4 == 0:
            if new_rings[i+1][0][1]-width < new_rings[i+1][1][1]:
                lower_extension_factor = new_rings[i+1][1][1]
            else:
                lower_extension_factor = new_rings[i+1][0][1]-width
            if new_rings[i+2][-1][1]+width > new_rings[i+2][-2][1]:
                upper_extension_factor = new_rings[i+2][-2][1]
            else:
                upper_extension_factor = new_rings[i+2][-1][1]+width
            extension_1 = (new_rings[i+1][0][0], lower_extension_factor) 
            extension_2 = (new_rings[i+2][-1][0], upper_extension_factor) 
            point1 = copy.deepcopy(new_rings[i+1][0])
            point2 = copy.deepcopy(new_rings[i+2][-1])
            point11 = (point1[0], point1[1]+width/2)
            point22 = (point2[0], point2[1]-width/2)
            m8_joint_points = [extension_1, point1, point11,  point22, point2, extension_2]
            cell.add(gdspy.FlexPath(snap_points(m8_joint_points), width, layer=layernames['M8'], datatype=layers['M8']['Draw']))
            #Left
            print(f"Find this {extension_1, extension_2}")
            draw_via(cell = cell,
                    ll =(  extension_1[0]-width/2, extension_1[1]),
                    ur = ( extension_1[0]+width/2,point1[1]),
                    layer_rules = layerspecs,
                    via_name = 'V8',
                    via_layer_num = layernames['V8'],
                    via_layer_datatype=layers['V8']['Draw'], 
                    move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                    )
            draw_via(cell = cell,
                    ll =( extension_2[0]-width/2,point2[1]),
                    ur = ( extension_2[0]+width/2, extension_2[1]),
                    layer_rules = layerspecs,
                    via_name = 'V8',
                    via_layer_num = layernames['V8'],
                    via_layer_datatype=layers['V8']['Draw'], 
                    move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                    )
            if num_turns % 2 == 0 and i + 4 > len(new_rings)-2:
                break

            if new_rings[i+3][-1][1] - width < new_rings[i+3][-2][1]:
                lower_extension_factor = new_rings[i+3][-2][1] 
            else:
                lower_extension_factor = new_rings[i+3][-1][1]-width

            if new_rings[i+4][0][1]+width > new_rings[i+4][1][1]:
                upper_extension_factor = new_rings[i+4][1][1]
            else:
                upper_extension_factor = new_rings[i+4][0][1]+width
            extension_1 = (new_rings[i+3][-1][0], new_rings[i+3][-1][1]) 
            extension_2 = (new_rings[i+4][0][0], upper_extension_factor) 
            point1 = copy.deepcopy((new_rings[i+3][-1][0],lower_extension_factor) )
            point2 = copy.deepcopy(new_rings[i+4][0])
            print(f"Final check : ",point1, extension_1, point2, extension_2)
            point11 = (extension_1[0], extension_1[1]+width/2)
            point22 = (point2[0], point2[1]-width/2)
            m8_joint_points = [  point1, extension_1, point11, point22, point2, extension_2]
            cell.add(gdspy.FlexPath(snap_points(m8_joint_points), width, layer=layernames['M8'], datatype=layers['M8']['Draw']))
            #Right
            draw_via(cell = cell,
                    ll =( extension_1[0]-width/2, point1[1]),
                    ur = ( extension_1[0]+width/2, extension_1[1]),
                    layer_rules = layerspecs,
                    via_name = 'V8',
                    via_layer_num = layernames['V8'],
                    via_layer_datatype=layers['V8']['Draw'], 
                    move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                    )
            draw_via(cell = cell,
                    ll =( extension_2[0]-width/2, point2[1]),
                    ur = ( extension_2[0]+width/2, extension_2[1]),
                    layer_rules = layerspecs,
                    via_name = 'V8',
                    via_layer_num = layernames['V8'],
                    via_layer_datatype=layers['V8']['Draw'], 
                    move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False
                    )
    #Port extension
    port_extension_length = port_extension_length + width/2
    if num_turns % 2 != 0:
        p1 = copy.deepcopy(new_rings[-2][-1])
        p2 = copy.deepcopy(new_rings[-1][0])
    else:
        p1 = copy.deepcopy(rings[-2][0])
        p2 = copy.deepcopy(rings[-1][-1])
    
    if num_turns%2 == 0:
        p1_extension = p1[0] + port_extension_length
        p2_extension = p2[0] + port_extension_length
        print(f'check this: {new_rings[-1]}')

        new_rings[-2].insert(0, (p1_extension, p1[1]))
        print(f'check this: {new_rings[-1]}')
        new_rings[-1].append((p2_extension, p2[1]))
        print(f'check this: {new_rings[-1]}')

    else:
        p1_extension = p1[0] - port_extension_length
        p2_extension = p2[0] - port_extension_length
        new_rings[-2].append((p1_extension, p1[1]))
        new_rings[-1].insert(0, (p2_extension, p2[1]))    
    if num_turns%2 == 0:
        draw_label(cell = cell,
                lower_ll = (p1_extension, p1[1]+width/2) ,
                lower_ur = (p1_extension - width, p1[1]-width/2),
                upper_ll = (p1_extension, p1[1]+width/2),
                upper_ur = (p1_extension - width, p1[1]-width/2),
                label_name="P1",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        draw_label(cell = cell,
                lower_ll = (p2_extension, p2[1]+width/2) ,
                lower_ur = (p2_extension - width, p2[1]-width/2),
                upper_ll = (p2_extension, p2[1]+width/2),
                upper_ur = (p2_extension - width, p2[1]-width/2),
                label_name="P2",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        if gen_routing == True:
            draw_label(cell = dummy_cell,
                    lower_ll = (p1_extension, p1[1]+width/2) ,
                    lower_ur = (p1_extension - width, p1[1]-width/2),
                    upper_ll = (p1_extension, p1[1]+width/2),
                    upper_ur = (p1_extension - width, p1[1]-width/2),
                    label_name="P1",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            draw_label(cell = dummy_cell,
                    lower_ll = (p2_extension, p2[1]+width/2) ,
                    lower_ur = (p2_extension - width, p2[1]-width/2),
                    upper_ll = (p2_extension, p2[1]+width/2),
                    upper_ur = (p2_extension - width, p2[1]-width/2),
                    label_name="P2",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            dummy_p1_m9 = gdspy.FlexPath(((p1_extension, p1[1]), (p1_extension - width, p1[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p1_m9)
            dummy_p2_m9 = gdspy.FlexPath(((p2_extension, p2[1]), (p2_extension - width, p2[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p2_m9)
    else:
        draw_label(cell = cell,
                lower_ll = (p1_extension, p1[1]+width/2) ,
                lower_ur = (p1_extension + width, p1[1]-width/2),
                upper_ll = (p1_extension, p1[1]+width/2),
                upper_ur = (p1_extension + width, p1[1]-width/2),
                label_name="P1",
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        draw_label(cell = cell,
                lower_ll = (p2_extension, p2[1]+width/2) ,
                lower_ur = (p2_extension + width, p2[1]-width/2),
                upper_ll = (p2_extension, p2[1]+width/2),
                label_name="P2",
                upper_ur = (p2_extension + width, p2[1]-width/2),
                label_layer= labellayers[layernames['M9']][0],
                label_datatype=labellayers[layernames['M9']][1]
                )
        if gen_routing == True:
            draw_label(cell = dummy_cell,
                    lower_ll = (p1_extension, p1[1]+width/2) ,
                    lower_ur = (p1_extension + width, p1[1]-width/2),
                    upper_ll = (p1_extension, p1[1]+width/2),
                    upper_ur = (p1_extension + width, p1[1]-width/2),
                    label_name="P1",
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            draw_label(cell = dummy_cell,
                    lower_ll = (p2_extension, p2[1]+width/2) ,
                    lower_ur = (p2_extension + width, p2[1]-width/2),
                    upper_ll = (p2_extension, p2[1]+width/2),
                    label_name="P2",
                    upper_ur = (p2_extension + width, p2[1]-width/2),
                    label_layer= labellayers[layernames['M9']][0],
                    label_datatype=labellayers[layernames['M9']][1]
                    )
            dummy_p1_m9 = gdspy.FlexPath(((p1_extension, p1[1]), (p1_extension + width, p1[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p1_m9)
            dummy_p2_m9 = gdspy.FlexPath(((p2_extension, p2[1]), (p2_extension + width, p2[1])), width, layer=layernames['M9'], datatype=layers['M9']['Draw'], tolerance=0.001, precision=0.001)
            dummy_cell.add(dummy_p2_m9)
    #symmetric
    
    if pgs == False:
        draw_shield_box(cell=cell,
                        spacing= max(abs(p2[0]),abs(p1[0]))+shield_space_from_p2 , coil_width=width,
                        shield_width= shield_metal_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], labellayers = labellayers, layers = layers, layernames = layernames,
                        follow_coil_shape = follow_coil_shape, num_sides = num_sides, num_turns=num_turns, elongation=elongation, coil_spacing=clearance)
        if gen_routing == True:
            obstacle_point = max(abs(p2[0]),abs(p1[0]))
            for l in ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9']:
                inductor_obstacle = gdspy.Rectangle((-obstacle_point+2*width, -obstacle_point+2*width), (obstacle_point-2*width, obstacle_point-2*width),layer=layernames[l], datatype=layers[l]['Draw'])        
                dummy_cell.add(inductor_obstacle)
            draw_shield_box(cell=dummy_cell,
                            spacing= max(abs(p2_extension),abs(p1_extension))+shield_space_from_p2 ,
                            shield_width= shield_metal_width, layer=layernames['M1'], datatype=layers['M1']['Draw'], this_is_dummy = True, bbox_layer=layernames['Bbox'], bbox_datatype=layers['Bbox']['Draw'], labellayers = labellayers, layers = layers, layernames = layernames)
        

    else:
        generate_patterned_ground_shield(cell=cell, shield_box_spacing=max(abs(p2_extension),abs(p1_extension))+shield_space_from_p2,  layerspecs=layerspecs, layer=layernames['M1'], datatype=layers['M1']['Draw'], labellayers= labellayers, layernames = layernames)
        if gen_routing == True:
            generate_patterned_ground_shield(cell=dummy_cell, shield_box_spacing=max(abs(p2_extension),abs(p1_extension))+shield_space_from_p2,  layerspecs=layerspecs, layer=layernames['M1'], datatype=layers['M1']['Draw'], this_is_dummy = True, labellayers= labellayers, layernames = layernames)
    
    #TILL HERE
    for ring in new_rings:
        spiral = gdspy.FlexPath(snap_points(ring), width, layer=layernames['M9'], datatype=layers['M9']['Draw'])
        cell.add(spiral)
    # Save GDS file
        bbox = cell.get_bounding_box()         # [[x_min,y_min],[x_max,y_max]]
    if bbox is None:
        raise ValueError('Cell is empty ? nothing to shift')
    (x_min, y_min), _ = bbox


    # Align to (0,0) by translating all shapes in-place
    bbox = cell.get_bounding_box()
            
    if bbox is not None:
        llx, lly = bbox[0]
        # dx, dy = -llx, -lly
        dx, dy = (0, 0)
    else:
        dx, dy = (0, 0)

    # Create a top cell with reference to shifted capacitor
    cell_to_export = gdspy.Cell(f'{gds_name}')
    cell_to_export.add(gdspy.CellReference(cell, (dx, dy)))

    out_path = os.path.join(output_dir, f"{gds_name}.gds")
    gdspy.write_gds(out_path, cells = [cell_to_export, cell])

    if gen_routing == True:
        bbox = dummy_cell.get_bounding_box()         # [[x_min,y_min],[x_max,y_max]]
        if bbox is None:
            raise ValueError('Cell is empty ? nothing to shift')
        (x_min, y_min), _ = bbox

        # 3. Translate every element in?place
        for poly in dummy_cell.polygons:             # all PolygonSet objects
            poly.translate(-x_min, -y_min)
        for path in dummy_cell.paths:                # all FlexPath/RobustPath objects
            path.translate(-x_min, -y_min)
        for ref in dummy_cell.references:            # all CellReference/CellArray objects
            ref.translate(-x_min, -y_min)
        for lbl in dummy_cell.labels:                # all Label objects
            lbl.translate(-x_min, -y_min)

    # Save GDS file
    # lib.write_gds(f'{output_dir}/{gds_name}.gds')
    if gen_routing == True:
        dummy_cell.name = gds_name
        # 2) Move it in the library?s dict
        dummy_lib.cells[gds_name] = dummy_lib.cells.pop(gds_name+'dummy')
        dummy_lib.write_gds(f'{args.output_dummy}/{gds_name}.gds')
    
    elapsed = time.time() - start
    print(f"Total time taken to generate the layout with the above specifications : {elapsed:.5f} seconds")
    print(f"Layout ready to view using the command : klayout {gds_name}.gds ")
    
    if if_cell_details == True:
        (x0, y0, x1, y1), w, h, pins = extract_cell_details(lib = lib, pin_order = ['P1','P2', 'GND'])
        return (x0, y0, x1, y1), w, h, pins 






def generate_patterned_ground_shield(cell,  shield_box_spacing, layer, layerspecs, datatype, labellayers, layernames, shield_box_width= None, draw_diameters = False, this_is_dummy = False):
    print(f"Generating the patterened shield ground.")
    # shield_box_width = 3
    gap = layerspecs['M1']['Pitch']
    if shield_box_width !=None:
        width = max(layerspecs['M1']['Width'],shield_box_width)
    else:
        width = layerspecs['M1']['Width']

    shield_box_coords = [
        (-shield_box_spacing, -shield_box_spacing),
        ( shield_box_spacing, -shield_box_spacing),
        ( shield_box_spacing,  shield_box_spacing),
        (-shield_box_spacing,  shield_box_spacing),
        (-shield_box_spacing, -shield_box_spacing-(width/2)),
    ]
    frame = gdspy.FlexPath(
        snap_points(shield_box_coords),
        width,
        layer=layer,
        datatype=datatype,
        ends='flush'
    )
    cell.add(frame)
    #Adding GND port to the shield box
    draw_label(cell = cell,
                lower_ll = (shield_box_spacing-width/2,-width/2) ,
                lower_ur = (shield_box_spacing + width/2, width/2) ,
                upper_ll = (shield_box_spacing-width/2,-width/2),
                upper_ur = (shield_box_spacing + width/2, width/2),
                label_name="GND",
                label_layer= labellayers[layernames['M1']][0],
                label_datatype=labellayers[layernames['M1']][1]
                )
    if this_is_dummy == True:
        dummy_p1_m9 = gdspy.FlexPath(((shield_box_spacing-width/2,-width/2), (shield_box_spacing + width/2, width/2)), width, layer=layernames['M1'], datatype=layers['M1']['Draw'], tolerance=0.001, precision=0.001)
        cell.add(dummy_p1_m9)
    

    shield_strip_coords = []
    y_initial = -shield_box_spacing
    y_final = -y_initial
    pitch = gap + width
    num_shields = int((y_final - y_initial) / pitch)

    avail_space_to_fill = y_final - y_initial
    if (pitch * num_shields) < avail_space_to_fill:
        y_initial = y_initial + (avail_space_to_fill - (pitch*num_shields))/2

    end_to_end_offset = width/2 + layerspecs['M1']['EndToEnd']
    #Right section
    y = y_initial + pitch
    shield_counter = 1
    while y < y_final and (y_final - y) >= pitch:
        if shield_counter <= num_shields/2:
            shield_strip_coords = [(shield_box_spacing, y), (-y+end_to_end_offset, y)]
        else:
            shield_strip_coords = [(shield_box_spacing, y), (y+end_to_end_offset, y)]

        shield_strip = gdspy.FlexPath(
        snap_points(shield_strip_coords),
        width,
        layer=layer,
        datatype=datatype,
        ends='flush'
        )
        cell.add(shield_strip)
        y += pitch
        shield_counter += 1


    #Left section
    y = y_initial + pitch
    shield_counter = 1
    while y < y_final and (y_final - y) >= pitch:
        if shield_counter <= num_shields/2:
            shield_strip_coords = [(-shield_box_spacing, y), (y-end_to_end_offset, y)]
        else:
            shield_strip_coords = [(-shield_box_spacing, y), (-y-end_to_end_offset, y)]
        shield_strip = gdspy.FlexPath(
        snap_points(shield_strip_coords),
        width,
        layer=layer,
        datatype=datatype,
        ends='flush'
        )
        cell.add(shield_strip)
        y += pitch
        shield_counter += 1

    #Bottom section
    y = y_initial + pitch
    shield_counter = 1
    while y < y_final and (y_final - y) >= pitch:
        if shield_counter <= num_shields/2:
            shield_strip_coords = [(y, -shield_box_spacing), (y, y-end_to_end_offset)]
        else:
            shield_strip_coords = [(y, -shield_box_spacing), (y, -y-end_to_end_offset)]
        shield_strip = gdspy.FlexPath(
        snap_points(shield_strip_coords),
        width,
        layer=layer,
        datatype=datatype,
        ends='flush'
        )
        cell.add(shield_strip)
        y += pitch
        shield_counter += 1

    #Top section
    y = y_initial + pitch
    shield_counter = 1
    while y < y_final and (y_final - y) >= pitch:
        if shield_counter <= num_shields/2:
            shield_strip_coords = [(y, shield_box_spacing), (y, -y+end_to_end_offset)]
        else:
            shield_strip_coords = [(y, shield_box_spacing), (y, y+end_to_end_offset)]
        shield_strip = gdspy.FlexPath(
        snap_points(shield_strip_coords),
        width,
        layer=layer,
        datatype=datatype,
        ends='flush'
        )
        cell.add(shield_strip)
        y += pitch
        shield_counter += 1

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate an octagonal spiral inductor with custom parameters"
    )

    parser.add_argument(
        "--pdk",
        type=str,
        required=True,
        help="Path to the PDK layers.json file (required)"
    )

    parser.add_argument(
        "--name",
        type=str,
        default="inductor",
        help="Output GDS base name (default: inductor)"
    )

    parser.add_argument(
        "--type",
        type=str,
        default="std",
        help="Inductor type: std or sym (default: std)"
    )

    parser.add_argument(
        "--num-turns", "-t",
        type=float,
        default=2.0,
        help="Total number of spiral windings. std supports quarter-turn increments; sym accepts whole numbers only. (default: 2.0)"
    )

    parser.add_argument(
        "--num-sides", "-s",
        type=int,
        default=8,
        help="Number of sides of the coil. std accepts integer; sym supports only even integer. (default: 8)"
    )

    parser.add_argument(
        "--inner_radius", "-r",
        type=float,
        default=50.0,
        help="Inner radius in um. (default: 50.0)"
    )

    parser.add_argument(
        "--clearance", "-c",
        type=float,
        default=5.0,
        help="Metal-to-metal clearance in um. (default: 5.0)"
    )

    parser.add_argument(
        "--width", "-w",
        type=float,
        default=5.0,
        help="Trace width in um. (default: 5.0)"
    )

    parser.add_argument(
        "--port_extension_length", "-port_len",
        type=float,
        default=20.0,
        help="Length of the port extension in um. (default: 10.0)"
    )

    parser.add_argument(
        "--shield_space_from_p2", "-shield_space",
        type=float,
        default=5.0,
        help="Shield spacing from terminals in um. (default: 5.0)"
    )

    parser.add_argument(
        "--shield_metal_width", "-shield_metal_width",
        type=float,
        default=15.0,
        help="Shield metal width in um. (default: 15.0)"
    )

    parser.add_argument(
        "--pgs",
        action="store_true",
        help="Enable patterned ground shield"
    )

    parser.add_argument(
        "-od", "--output_dummy",
        type=Path,
        default=Path("output_gds_dummy/"),
        help="Directory to write routing/dummy GDS files (default: output_gds_dummy/)"
    )

    parser.add_argument(
        "-or", "--output_real",
        type=Path,
        default=Path("examples/"),
        help="Directory to write final layout GDS files (default: output_gds_real/)"
    )

    parser.add_argument(
        "--gen_routing",
        action="store_true",
        help="Generate extra dummy layout for routing purpose"
    )

    parser.add_argument(
        "--emx_only",
        action="store_false",
        help="Generate EMX friendly layout"
    )
    parser.add_argument("--scale",  type=float, default=1000.0,
                        help="Scaling factor (default: 1000)")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 90)
    print("Octagonal spiral inductor GDS generator")
    print("=" * 90)
    print(f"PDK file               : {args.pdk}")
    print(f"Requested layout type  : {args.type}")
    print(f"Inductor name          : {args.name}")
    print(f"Turns                  : {args.num_turns}")
    print(f"Sides                  : {args.num_sides}")
    print(f"Inner radius (um)      : {args.inner_radius}")
    print(f"Clearance (um)         : {args.clearance}")
    print(f"Metal width (um)       : {args.width}")
    print(f"Port extension (um)    : {args.port_extension_length}")
    print(f"Shield spacing (um)    : {args.shield_space_from_p2}")
    print(f"Shield width (um)      : {args.shield_metal_width}")
    print(f"PGS enabled            : {args.pgs}")
    print(f"Generate routing GDS   : {args.gen_routing}")
    print(f"Real output directory  : {args.output_real}")
    print(f"Dummy output directory : {args.output_dummy}")
    print()
    print("Example runs:")
    print(f"  Standard  : python {script_name} --pdk /path/to/layers.json")
    print(f"  Symmetric : python {script_name} --pdk /path/to/layers.json --type sym")
    print(f"  Custom    : python {script_name} --pdk /path/to/layers.json --name L1 --num-turns 3 --inner_radius 60")
    print("=" * 90)

    if not os.path.exists(args.pdk):
        raise FileNotFoundError(f"PDK file not found: {args.pdk}")

    os.makedirs(args.output_real, exist_ok=True)
    if args.gen_routing:
        os.makedirs(args.output_dummy, exist_ok=True)

    print("\nReading PDK layer information...")
    layers, layernames, labellayers, layerspecs, design_info = read_pdk.readLayerInfo(args.pdk, scale=args.scale)
    print("PDK layer information loaded successfully.")

    if args.type == "std":
        print("\nGenerating standard inductor layout...")
        generate_standard_inductor(
            num_turns=args.num_turns,
            inner_radius=args.inner_radius,
            clearance=args.clearance,
            port_extension_length=args.port_extension_length,
            width=args.width,
            num_sides=args.num_sides,
            shield_space_from_p2=args.shield_space_from_p2,
            shield_metal_width=args.shield_metal_width,
            layers=layers,
            layernames=layernames,
            labellayers=labellayers,
            layerspecs=layerspecs,
            output_dir=str(args.output_real),
            pgs=args.pgs,
            gds_name=args.name,
            gen_routing=args.gen_routing
        )

    elif args.type == "sym":
        print("\nGenerating symmetric inductor layout...")
        generate_symmetric_inductor(
            num_turns=args.num_turns,
            inner_radius=args.inner_radius,
            clearance=args.clearance,
            port_extension_length=args.port_extension_length,
            width=args.width,
            num_sides=args.num_sides,
            shield_space_from_p2=args.shield_space_from_p2,
            shield_metal_width=args.shield_metal_width,
            layers=layers,
            layernames=layernames,
            labellayers=labellayers,
            layerspecs=layerspecs,
            output_dir=str(args.output_real),
            pgs=args.pgs,
            gds_name=args.name,
            gen_routing=args.gen_routing
        )

    else:
        raise ValueError(f"Unsupported --type '{args.type}'. Allowed values are 'std' or 'sym'.")

    print("\nDone.")
    print(f"Real layout written to : {args.output_real / (args.name + '.gds')}")
    if args.gen_routing:
        print(f"Routing layout written : {args.output_dummy / (args.name + '.gds')}")

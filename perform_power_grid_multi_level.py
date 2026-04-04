#!/usr/bin/env python3

import gdspy
import numpy as np
import argparse
import sys
import networkx as nx
import math
import json
import os

import numpy as np
from shapely.geometry import Polygon, Point 

def load_config(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
    return cfg

#Reading layers.json file
def readLayerInfo(layerfile, scale): 
    layers_specs_sacle = scale
    design_info = dict()
    layers = dict()
    layerSpecs = dict()
    layernames = dict()
    labellayers = dict()
    with open(layerfile) as fp:
        layerdata = json.load(fp)
        if "Abstraction" in layerdata:
            for l in layerdata["Abstraction"]:
                if "Layer" in l and "GdsLayerNo" in l:# and "Direction" in l:
                    layer = l["Layer"]      #Layer Name (M1)
                    glno1 = l["GdsLayerNo"]    #Layer no. (15)
                    glno2 = dict()  #Dict for storing different datatypes of layer
                    specs = dict()
                    layernames[layer] = glno1   #Dict of layernames where key is layer number and value is layer name
                    if "GdsDatatype" in l:
                        for key, idx in l["GdsDatatype"].items():
                            glno2[key] = idx    #Storing values of gds data types where key is the Data type No (32) (idx) and  value is the data type name (Pin) (key)
                            if "Label"== key:   #If its data type of "Label"
                                labellayers[glno1] = (glno1, idx) #e.g. labelayers[(17,20)] = 17 WHICH IS FOR M2 Label
                            elif "Pin"== key:
                                labellayers[glno1] = (glno1, idx) #e.g. labellayers[(17,32)] = 17 WHICH IS FOR M2 Pin
                    if "LabelLayerNo" in l:
                        for ll in l["LabelLayerNo"]:
                            if len(ll) == 2:
                                labellayers[glno1] = (ll[0], ll[1])
                            elif len(ll) == 1:
                                labellayers[glno1] = (ll[0], 0)
                    layers[layer] = glno2
                    if "Width" in l:
                        specs["Width"] = l["Width"]/layers_specs_sacle
                    if "WidthX" in l:
                        specs["WidthX"] = l["WidthX"]/layers_specs_sacle
                    if "WidthY" in l:
                        specs["WidthY"] = l["WidthY"]/layers_specs_sacle
                    if "SpaceX" in l:
                        specs["SpaceX"] = l["SpaceX"]/layers_specs_sacle
                    if "SpaceY" in l:
                        specs["SpaceY"] = l["SpaceY"]/layers_specs_sacle
                    if "Pitch" in l:
                        specs["Pitch"] = l["Pitch"]/layers_specs_sacle
                    if "VencA_L" in l:
                        specs["VencA_L"] = l["VencA_L"]/layers_specs_sacle
                    if "VencA_H" in l:
                        specs["VencA_H"] = l["VencA_H"]/layers_specs_sacle
                    if "VencP_L" in l:
                        specs["VencP_L"] = l["VencP_L"]/layers_specs_sacle
                    if "VencP_H" in l:
                        specs["VencP_H"] = l["VencP_H"]/layers_specs_sacle
                    if "Direction" in l:
                        specs["Direction"] = l["Direction"]
                    if "EndToEnd" in l:
                        specs["EndToEnd"] = l["EndToEnd"]/layers_specs_sacle
                    layerSpecs[layer] = specs

        if "design_info" in layerdata:
            for _ in layerdata["design_info"]:
                if "vdd_grid_top_layer" in  layerdata["design_info"]:
                    design_info["vdd_grid_top_layer"] =  layerdata["design_info"]["vdd_grid_top_layer"]
                if "vdd_grid_bottom_layer" in layerdata["design_info"]:
                    design_info["vdd_grid_bottom_layer"] =  layerdata["design_info"]["vdd_grid_bottom_layer"]
                if "gnd_grid_top_layer" in layerdata["design_info"]:
                    design_info["gnd_grid_top_layer"] = layerdata["design_info"]["gnd_grid_top_layer"]
                if "gnd_grid_bottom_layer" in layerdata["design_info"]:
                    design_info["gnd_grid_bottom_layer"] = layerdata["design_info"]["gnd_grid_bottom_layer"]
    return (layers, layernames, labellayers, layerSpecs, design_info)



layers = {}
layernames = {}
labellayers = {}
layerSpecs = {} 
design_info = {}
inverse_layers = {}


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

def place_decaps_from_grid_with_gds_orig(all_points, obs_polygons, decap_gds_path, decap_cell_name,
                                    gap, xmin, ymin, xmax, ymax, num_decaps):
    """
    Places references to a real DECAP GDS cell at valid grid points.
    Automatically reads decap size (W,H) and origin offset from the GDS.
    Returns a list of gdspy.CellReference objects.
    """
    import numpy as np
    import gdspy

    def aabb_intersect(ll1, ur1, ll2, ur2, margin=0.0):
        # True if rectangles overlap when each is expanded by margin outward
        return not (ur1[0] < ll2[0] - margin or ll1[0] > ur2[0] + margin or
                    ur1[1] < ll2[1] - margin or ll1[1] > ur2[1] + margin)

    print(f"Starting DECAP GDS placement from {decap_gds_path}")

    lib_decap = gdspy.GdsLibrary()
    lib_decap.read_gds(decap_gds_path)
    if decap_cell_name not in lib_decap.cells:
        raise ValueError(f"Cell '{decap_cell_name}' not found in {decap_gds_path}")

    decap_cell = lib_decap.cells[decap_cell_name]
    decap_bbox = decap_cell.get_bounding_box()
    if decap_bbox is None:
        raise ValueError(f"Could not extract bounding box for decap cell '{decap_cell_name}'")

    # Decap width and height
    decap_w = float(decap_bbox[1][0] - decap_bbox[0][0])
    decap_h = float(decap_bbox[1][1] - decap_bbox[0][1])

    # Offset of the cell internal origin relative to its LL bbox
    # If the geometry is not at (0,0), you must compensate this when placing the reference
    off_llx, off_lly = float(decap_bbox[0][0]), float(decap_bbox[0][1])

    print(f"Loaded decap cell '{decap_cell_name}' ({decap_w:.3f} x {decap_h:.3f} um), origin offset LL=({off_llx:.3f},{off_lly:.3f})")

    points = np.array(all_points, dtype=float)
    if points.size == 0:
        print("No grid points available for decap placement.")
        return []

    # Candidate window of the chip
    chip_ll = (float(xmin), float(ymin))
    chip_ur = (float(xmax), float(ymax))

    # Quick reject against obstacles at the point level using your gap
    def point_clear_of_obs(px, py):
        # Build the would-be decap box centered at point
        ll = (px - decap_w / 2, py - decap_h / 2)
        ur = (px + decap_w / 2, py + decap_h / 2)

        # Check chip boundary
        if ll[0] < xmin or ur[0] > xmax or ll[1] < ymin or ur[1] > ymax:
            return False

        # Check each obstacle polygon
        for poly in obs_polygons or []:
            if poly is None:
                continue
            # Convert numpy arrays to lists for uniform handling
            if isinstance(poly, np.ndarray):
                if poly.size == 0:
                    continue
                poly = poly.tolist()
            # Skip if not enough points
            if len(poly) < 3:
                continue

            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            obs_ll = (min(xs), min(ys))
            obs_ur = (max(xs), max(ys))
            if aabb_intersect(ll, ur, obs_ll, obs_ur, margin=gap):
                return False

        return True


    # Filter candidate points
    valid_points = [(float(x), float(y)) for x, y in points if point_clear_of_obs(float(x), float(y))]
    print(f"After obstacle filtering: {len(valid_points)} candidate points remain")

    if not valid_points:
        print("All points blocked, nothing to place.")
        return []

    chosen = []
    # For AABB based spacing between decaps, use true rectangle sizes plus gap
    # We will test rectangle overlap directly rather than a single scalar spacing
    def overlaps_existing(px, py):
        ll1 = (px - decap_w / 2, py - decap_h / 2)
        ur1 = (px + decap_w / 2, py + decap_h / 2)
        for (cx, cy) in chosen:
            ll2 = (cx - decap_w / 2, cy - decap_h / 2)
            ur2 = (cx + decap_w / 2, cy + decap_h / 2)
            if aabb_intersect(ll1, ur1, ll2, ur2, margin=gap):
                return True
        return False

    for (x, y) in valid_points:
        if overlaps_existing(x, y):
            continue
        chosen.append((x, y))
        if num_decaps and len(chosen) >= num_decaps:
            break

    print(f"Selected {len(chosen)} legal points for DECAP placement")

    # Build references; compensate for cell internal origin offset so that the placed bbox centers at (x,y)
    decap_refs = []
    for i, (x, y) in enumerate(chosen):
        # We want the decap LL at (x - w/2, y - h/2). Since the cell origin is at (0,0) relative to its shapes,
        # and the LL bbox is at (off_llx, off_lly), set the reference origin so that (origin + off_ll) == desired LL.
        origin_x = (x - decap_w / 2) - off_llx
        origin_y = (y - decap_h / 2) - off_lly
        ref = gdspy.CellReference(decap_cell, (origin_x, origin_y))
        decap_refs.append(ref)

    print(f"Created {len(decap_refs)} DECAP references within chip [{xmin},{ymin}] to [{xmax},{ymax}]")
    if decap_refs:
        example = [(float(r.origin[0]), float(r.origin[1])) for r in decap_refs[:3]]
        print(f"Example DECAP origins (already offset-compensated): {example}")

    return decap_refs


import numpy as np
import gdspy
# ADDED SHAPELY IMPORTS
from shapely.geometry import Polygon, box

def place_decaps_from_grid_with_gds(all_points, obs_polygons, decap_gds_path, decap_cell_name,
                                    gap, xmin, ymin, xmax, ymax, num_decaps):
    """
    Places references to a real DECAP GDS cell at valid grid points.
    Uses accurate geometric intersection for obstacle checking and AABB margin for decap spacing.
    Returns a list of gdspy.CellReference objects.
    """

    def aabb_intersect(ll1, ur1, ll2, ur2, margin=0.0):
        # True if rectangles overlap when each is expanded by margin outward
        # This function is used for fast DECAP-to-DECAP spacing check
        return not (ur1[0] < ll2[0] - margin or ll1[0] > ur2[0] + margin or
                    ur1[1] < ll2[1] - margin or ll1[1] > ur2[1] + margin)

    print(f"Starting DECAP GDS placement from {decap_gds_path}")

    lib_decap = gdspy.GdsLibrary()
    lib_decap.read_gds(decap_gds_path)
    if decap_cell_name not in lib_decap.cells:
        raise ValueError(f"Cell '{decap_cell_name}' not found in {decap_gds_path}")

    decap_cell = lib_decap.cells[decap_cell_name]
    decap_bbox = decap_cell.get_bounding_box()
    if decap_bbox is None:
        raise ValueError(f"Could not extract bounding box for decap cell '{decap_cell_name}'")

    # Decap width and height
    decap_w = float(decap_bbox[1][0] - decap_bbox[0][0])
    decap_h = float(decap_bbox[1][1] - decap_bbox[0][1])

    # Offset of the cell internal origin relative to its LL bbox
    off_llx, off_lly = float(decap_bbox[0][0]), float(decap_bbox[0][1])

    print(f"Loaded decap cell '{decap_cell_name}' ({decap_w:.3f} x {decap_h:.3f} um), origin offset LL=({off_llx:.3f},{off_lly:.3f})")

    points = np.array(all_points, dtype=float)
    if points.size == 0:
        print("No grid points available for decap placement.")
        return []

    # Handle num_decaps being None, default to 0 (which means place all available)
    if num_decaps is None:
        num_decaps = 0

    # --- Pre-process and Buffer Obstacles (New/Improved Logic) ---
    expanded_obs_polygons = []
    for poly in obs_polygons or []:
        if poly is None or (isinstance(poly, np.ndarray) and poly.size == 0):
            continue
        if isinstance(poly, np.ndarray):
             poly = poly.tolist()
        if len(poly) >= 3:
            original_obs = Polygon(poly)
            # Create the accurate exclusion zone by buffering (expanding) the obstacle
            expanded_obs_polygons.append(original_obs.buffer(gap, join_style=2))

    # --- Geometric Obstacle Check (Modified Logic) ---
    def point_clear_of_obs(px, py):
        # Build the would-be decap box center at point (px, py)
        llx = px - decap_w / 2
        lly = py - decap_h / 2
        urx = px + decap_w / 2
        ury = py + decap_h / 2

        # Check chip boundary
        if llx < xmin or urx > xmax or lly < ymin or ury > ymax:
            return False

        # Create a Shapely rectangle representing the DECAP at this location
        decap_box = box(llx, lly, urx, ury)

        # Check each *expanded* obstacle polygon for intersection
        for expanded_obs in expanded_obs_polygons:
            # Replaces the old AABB intersection check with an accurate geometric check
            if decap_box.intersects(expanded_obs): 
                return False

        return True

    # --- Filtering and Iterative Spacing Logic (Original Flow Preserved) ---
    
    # Filter candidate points
    valid_points = [(float(x), float(y)) for x, y in points if point_clear_of_obs(float(x), float(y))]
    print(f"After obstacle filtering: {len(valid_points)} candidate points remain")

    if not valid_points:
        print("All points blocked, nothing to place.")
        return []

    chosen = []
    
    # This DECAP-to-DECAP spacing check is kept AABB-based with margin for speed
    def overlaps_existing(px, py):
        # Current DECAP AABB
        ll1 = (px - decap_w / 2, py - decap_h / 2)
        ur1 = (px + decap_w / 2, py + decap_h / 2)
        
        for (cx, cy) in chosen:
            # Existing DECAP AABB
            ll2 = (cx - decap_w / 2, cy - decap_h / 2)
            ur2 = (cx + decap_w / 2, cy + decap_h / 2)
            # Check for overlap, requiring margin clearance
            if aabb_intersect(ll1, ur1, ll2, ur2, margin=gap):
                return True
        return False

    for (x, y) in valid_points:
        if overlaps_existing(x, y):
            continue
        chosen.append((x, y))
        # Ensure num_decaps is checked properly (handles the previously raised TypeError)
        if num_decaps > 0 and len(chosen) >= num_decaps:
            break

    print(f"Selected {len(chosen)} legal points for DECAP placement")

    # Build references; compensate for cell internal origin offset
    decap_refs = []
    for i, (x, y) in enumerate(chosen):
        # We want the decap LL at (x - w/2, y - h/2). 
        origin_x = (x - decap_w / 2) - off_llx
        origin_y = (y - decap_h / 2) - off_lly
        ref = gdspy.CellReference(decap_cell, (origin_x, origin_y))
        decap_refs.append(ref)

    print(f"Created {len(decap_refs)} DECAP references within chip [{xmin},{ymin}] to [{xmax},{ymax}]")
    if decap_refs:
        example = [(float(r.origin[0]), float(r.origin[1])) for r in decap_refs[:3]]
        print(f"Example DECAP origins (already offset-compensated): {example}")

    return decap_refs
def filter_valid_points_orig(points, obs_polygon, gap):
    """
    Vectorized OR-based check for many points at once.
    Removes any point that lies inside at least one polygon (union).
    
    Args:
        points (ndarray): shape (N,2), array of (x,y) points.
        obs_polygon (list): list of polygons, each with 4 (x,y) tuples.
        poly_w (float): margin expansion for obstacles.
    
    Returns:
        ndarray: filtered points that are valid (outside all polygons).
    """
    print(f"Using gap of {gap}")
    if not obs_polygon:
        return points  # nothing to block
    
    mask_valid = np.ones(len(points), dtype=bool)

    px = points[:, 0]
    py = points[:, 1]

    # Loop over polygons, but apply check to all points in one shot
    for poly in obs_polygon:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        xmin = min(xs) - gap
        xmax = max(xs) + gap
        ymin = min(ys) - gap
        ymax = max(ys) + gap

        inside = (px >= xmin) & (px <= xmax) & (py >= ymin) & (py <= ymax)
        mask_valid[inside] = False
    return points[mask_valid]


def filter_valid_points(points, obs_polygon, gap):
    """
    Vectorized OR-based check for many points at once, optimized with an AABB pre-filter.
    Removes any point that lies inside the actual polygon shape, 
    expanded by the given margin (gap).
    
    Args:
        points (ndarray): shape (N,2), array of (x,y) points.
        obs_polygon (list): list of polygons, each with (x,y) tuples.
        gap (float): margin expansion for obstacles.
    
    Returns:
        ndarray: filtered points that are valid (outside all polygons).
    """
    print(f"Using gap of {gap}")
    if not obs_polygon:
        return points # nothing to block
    
    # Initialize a mask assuming all points are valid
    mask_valid = np.ones(len(points), dtype=bool)

    # Separate coordinates for fast NumPy Bounding Box check
    px = points[:, 0]
    py = points[:, 1]
    
    # Loop over polygons
    for poly_coords in obs_polygon:
        # Convert to NumPy array for fast calculations
        poly_arr = np.array(poly_coords)
        
        # 1. Fast Pre-Filter: Calculate the Bounding Box (AABB) and expand it by 'gap'
        xmin_obs = np.min(poly_arr[:, 0]) - gap
        xmax_obs = np.max(poly_arr[:, 0]) + gap
        ymin_obs = np.min(poly_arr[:, 1]) - gap
        ymax_obs = np.max(poly_arr[:, 1]) + gap

        # Identify indices of points that are inside the *Expanded Bounding Box*
        # These are the only candidates that need the expensive geometric check.
        candidate_indices = np.where(
            (px >= xmin_obs) & (px <= xmax_obs) & 
            (py >= ymin_obs) & (py <= ymax_obs) & 
            mask_valid # Only check points that haven't been disqualified yet
        )[0]
        
        # Skip the expensive check if no points are near this obstacle
        if candidate_indices.size == 0:
            continue
            
        # 2. **Accurate Geometric Check (Only on Candidates)**
        
        # Create the original polygon and the expanded obstacle zone
        original_poly = Polygon(poly_coords)
        expanded_obs = original_poly.buffer(gap, join_style=2)
        
        # Get the actual candidate points
        candidate_points = points[candidate_indices]
        
        # Convert candidates to Shapely Points
        shapely_candidates = [Point(p) for p in candidate_points]

        # Check which candidates are inside the expanded obstacle
        # 'inside_candidates_mask' is relative to the small list of candidates
        inside_candidates_mask = np.array([expanded_obs.contains(p) for p in shapely_candidates])

        # 3. Update the main validity mask
        # Get the indices (in the original 'points' array) that are invalid
        invalid_indices = candidate_indices[inside_candidates_mask]
        
        # Disqualify them in the main mask
        mask_valid[invalid_indices] = False
            
    # Return only the points that remain valid
    return points[mask_valid]


def _prune_graph_to_boundary(G, direction="H"):
    """
    Prunes a graph to keep only components connected to the geometric boundary,
    aware of routing direction.

    Args:
        G (nx.Graph): Input graph (nodes are (x,y) tuples).
        direction (str): 'H' for horizontal routing, 'V' for vertical routing.

    Returns:
        nx.Graph: New graph containing only the nodes from boundary-connected components.
    """
    all_points = list(G.nodes())
    if not all_points:
        return nx.Graph()

    # Geometric bounding box
    x_coords = [p[0] for p in all_points]
    y_coords = [p[1] for p in all_points]
    xmin, xmax = min(x_coords), max(x_coords)
    ymin, ymax = min(y_coords), max(y_coords)

    # Boundary nodes depend on routing direction
    if direction.upper() == "V":
        # Vertical routing cares about top/bottom
        boundary_nodes = {p for p in all_points if p[1] == ymin or p[1] == ymax}
    else:  # default horizontal
        # Horizontal routing cares about left/right
        boundary_nodes = {p for p in all_points if p[0] == xmin or p[0] == xmax}

    # Find connected components
    connected_components = list(nx.connected_components(G))

    # Keep only components touching relevant boundary
    main_network_nodes = set()
    for component in connected_components:
        if not boundary_nodes.isdisjoint(component):
            main_network_nodes.update(component)

    return G.subgraph(main_network_nodes).copy()

def create_graph_manhattan_path(all_points, layer, datatype, cell,
                                line_width=1.0, connection_threshold=None,
                                direction='H', alt_layer=None, alt_datatype=None):
    """
    Builds a graph from all points and draws every edge as a Manhattan path.
    Also returns all coordinates where edges are drawn.
    """
    grid_points = []
    if not all_points or len(all_points) < 2:
        print("Error: At least two points are required to build a graph.")
        return cell, []

    # --- 1. Determine Connection Threshold ---
    if connection_threshold is None:
        min_dist = float('inf')
        sample_size = min(len(all_points), 100)
        for i in range(sample_size):
            for j in range(i + 1, sample_size):
                dist = math.sqrt((all_points[i][0] - all_points[j][0])**2 +
                                 (all_points[i][1] - all_points[j][1])**2)
                if dist > 1e-9:
                    min_dist = min(min_dist, dist)
        connection_threshold = 1.0 if min_dist == float('inf') else min_dist * 1.5
        print(f"Auto-detected connection threshold: {connection_threshold:.2f}")
    connection_threshold += 1e-6

    # --- 2. Build Graph using Efficient Spatial Hashing ---
    G = nx.Graph()
    G.add_nodes_from(all_points)
    grid = {}
    cell_size = connection_threshold

    for p in all_points:
        cell_x, cell_y = int(p[0] // cell_size), int(p[1] // cell_size)
        grid.setdefault((cell_x, cell_y), []).append(p)

    for p1 in all_points:
        cell_x, cell_y = int(p1[0] // cell_size), int(p1[1] // cell_size)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                neighbor_cell = (cell_x + dx, cell_y + dy)
                if neighbor_cell not in grid:
                    continue
                for p2 in grid[neighbor_cell]:
                    if p1 >= p2:
                        continue
                    dist = math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
                    if dist <= connection_threshold:
                        if direction == 'V' and p1[0] == p2[0]:
                            G.add_edge(p1, p2, weight=dist)
                        elif direction == 'H' and p1[1] == p2[1]:
                            G.add_edge(p1, p2, weight=dist)

    # --- Prune the Graph ---
    G = _prune_graph_to_boundary(G, direction=direction)

    # --- 3. Draw All Edges & Collect Drawn Points ---
    buffer_len = line_width /2  # µm
    drawn_points = set()
    # print(f"Drawing {len(G.edges())} edges from the graph.")
    for p_start, p_end in G.edges():
        this_layer = layer
        this_datatype = datatype

        # store original (non-buffered) points
        drawn_points.update([p_start, p_end])

        # apply buffer only for drawing
        if abs(p_start[0] - p_end[0]) > abs(p_start[1] - p_end[1]):
            # horizontal
            dx = buffer_len if p_end[0] > p_start[0] else -buffer_len
            p_start_buf = (p_start[0] - dx, p_start[1])
            p_end_buf   = (p_end[0] + dx, p_end[1])
        else:
            # vertical
            dy = buffer_len if p_end[1] > p_start[1] else -buffer_len
            p_start_buf = (p_start[0], p_start[1] - dy)
            p_end_buf   = (p_end[0], p_end[1] + dy)

        # Manhattan path construction
        if p_start_buf[0] == p_end_buf[0] or p_start_buf[1] == p_end_buf[1]:
            points = [p_start_buf, p_end_buf]
        else:
            corner_point = (p_end_buf[0], p_start_buf[1])
            points = [p_start_buf, corner_point, p_end_buf]

        cell.add(gdspy.FlexPath(points, width=line_width, layer=this_layer, datatype=this_datatype))



    # --- Return both cell and drawn points ---
    return cell, list(drawn_points)

def convex_hull(points):
    """
    Minimal monotonic chain convex hull.
    points: Nx2 numpy array
    returns hull as Nx2 array in CCW order.
    """
    pts = np.asarray(points)
    pts = pts[np.lexsort((pts[:,1], pts[:,0]))]  # sort by x, then y

    # Build lower hull
    lower = []
    for p in pts:
        while len(lower) >= 2:
            cross = ((lower[-1][0] - lower[-2][0]) * (p[1] - lower[-2][1]) -
                     (lower[-1][1] - lower[-2][1]) * (p[0] - lower[-2][0]))
            if cross <= 0:
                lower.pop()
            else:
                break
        lower.append(tuple(p))

    # Build upper hull
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2:
            cross = ((upper[-1][0] - upper[-2][0]) * (p[1] - upper[-2][1]) -
                     (upper[-1][1] - upper[-2][1]) * (p[0] - upper[-2][0]))
            if cross <= 0:
                upper.pop()
            else:
                break
        upper.append(tuple(p))

    hull = np.array(lower[:-1] + upper[:-1])
    return hull


def place_vias_between_layers(cell, vdd_via_dict, via_layer, via_datatype, via_name,
                              via_size=0.5, tol=0.005, metal_width = 2):
    """
    Places vias between overlapping grid points of neighboring metal layers.

    Args:
        cell (gdspy.Cell): The target cell to add via geometries into.
        vdd_via_dict (dict): {layer_num: [(x, y), ...]} mapping of grid points per layer.
        via_layer (int): GDS layer number for via placement.
        via_datatype (int): GDS datatype number for via placement.
        via_size (float): Side length of via square (default 0.5 µm).
        tol (float): Distance tolerance for overlap detection (default ±0.5 µm).

    Returns:
        tuple:
            gdspy.Cell ? The modified cell with vias added.
            list of (x, y, lower_layer, upper_layer) ? All via placement coordinates.
    """
    from scipy.spatial import cKDTree
    vias_added = []
    layer_keys = sorted(vdd_via_dict.keys())

    for i in range(len(layer_keys) - 1):
        lower = layer_keys[i]
        print(lower)
        upper = layer_keys[i + 1]
        print(upper)
        

        pts_lower = np.array(vdd_via_dict[lower])
        pts_upper = np.array(vdd_via_dict[upper])

        if pts_lower.size == 0 or pts_upper.size == 0:
            continue

        # Build KDTree for fast proximity matching
        tree_upper = cKDTree(pts_upper)

        # For each lower-layer point, find nearby upper-layer points
        matches = tree_upper.query_ball_point(pts_lower, tol)
        for idx_lower, matched_idxs in enumerate(matches):
            if not matched_idxs:
                continue
            x, y = pts_lower[idx_lower]
            via_center = (float(x), float(y))
            # Define via geometry (square)
            half = metal_width
            cell = insert_via(cell, (via_center[0] - half, via_center[1] - half), (via_center[0] + half, via_center[1] + half), layer_rules=layerSpecs, via_name= via_name, via_layer_num = layernames[via_name], via_layer_datatype=layers[via_name]['Draw'], move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False)
            vias_added.append((via_center[0], via_center[1], lower, upper))

    print(f"Placed {len(vias_added)} vias across {len(layer_keys) - 1} layer pairs.")
    return cell, vias_added

def debug_draw_points(cell, points, layer=900, datatype=0, size=0.2):
    """
    Draws tiny squares at each point for visual sanity check.
    layer=900 is arbitrary and guaranteed not to conflict with PDK layers.
    """
    half = size / 2.0
    for (x, y) in points:
        cell.add(gdspy.Rectangle((x - half, y - half),
                                 (x + half, y + half),
                                 layer=layer, datatype=datatype))


def add_edge_labels(cell, text, xmin, ymin, xmax, ymax, pitch, layer, datatype, direction='H'):
    """
    Adds label text along the chip edges at regular pitch spacing.

    Args:
        cell (gdspy.Cell): target cell to add labels to
        xmin, ymin, xmax, ymax (float): layout bounding box
        pitch (float): spacing between labels
        layer (int): GDS layer number for label
        datatype (int): GDS datatype for label
        direction (str): 'H' for horizontal grid, 'V' for vertical grid
    """
    label_offset = 5.0   # µm inward from chip edge for visibility

    if direction.upper() == 'H':
        # Labels along left and right edges for each horizontal gridline
        y_positions = np.arange(ymin + pitch, ymax, pitch)
        for y in y_positions:
            cell.add(gdspy.Label(text, position=(xmin + label_offset, y),
                                 layer=layer, texttype=datatype))
            cell.add(gdspy.Label(text, position=(xmax - label_offset, y),
                                 layer=layer, texttype=datatype))

    elif direction.upper() == 'V':
        # Labels along top and bottom edges for each vertical gridline
        x_positions = np.arange(xmin + pitch, xmax, pitch)
        for x in x_positions:
            cell.add(gdspy.Label(text, position=(x, ymin + label_offset),
                                 layer=layer, texttype=datatype))
            cell.add(gdspy.Label(text, position=(x, ymax - label_offset),
                                 layer=layer, texttype=datatype))



def main():
    global layers, layernames, labellayers, layerSpecs, design_info, inverse_layers
    # -------------------------
    # Step 1: Parse arguments
    # -------------------------
    parser = argparse.ArgumentParser(description="Place continuous parallel polygons in empty margin area around a layout")
    parser.add_argument("--infile", help="Input GDS file")
    parser.add_argument("--top", help="Top cell name (optional)")
    parser.add_argument("-o", "--outfile", help="Output GDS file", default="output_with_grid.gds")
    parser.add_argument("--config", default="config.json", help="Input config.json with all user inputs")
    parser.add_argument(
        "--io-direction",
        nargs="+",
        default=["N", "W", "E", "S"],
        choices=["N", "S", "E", "W"],
        help="List of IO directions to use. Example: --io-direction N W E S"
    )
    args = parser.parse_args()
    cfg = load_config(args.config)


    layers, layernames, labellayers, layerSpecs, design_info = readLayerInfo(cfg["pdk"], scale = cfg["scale"])
    for k, v in layernames.items():
        if v not in inverse_layers:
            inverse_layers[v] = k
    print(f"\nLAYERS : ",layers)
    print(f"\nLAYER NAMES : ",layernames)
    print(f"\nLABEL LAYERS : ",labellayers)
    print(f"\nLAYER SPECS : ",layerSpecs)
    print(f"\nDESIGN INFO : ",design_info)

    obs_specs = [(31, 0),(1001, 0)]
    poly_w = cfg["pdn"]["pdn_width"]
    pitch_x = cfg["pdn"]["pdn_gap"]+ poly_w

    # -------------------------
    # Step 2: Load GDS + get top cell
    # -------------------------
    lib = gdspy.GdsLibrary()
    lib.read_gds(args.infile)
    top = lib.cells[args.top] if args.top and args.top in lib.cells else lib.top_level()[0]
    bbox = top.get_bounding_box()

    stage_2_design = os.path.join(cfg["project_name"],"stage_2",f"{cfg['topcell']}_design.json")
    with open(stage_2_design, "r") as f:
        stage_2_design_json = json.load(f)

    io_height = stage_2_design_json["chip"]["io_h"]/cfg["scale"] #+ 4
    io_direction = args.io_direction
    buff = io_height
    (xmin, ymin), (xmax, ymax) = bbox
    if 'E' in io_direction: xmax -= buff
    if 'W' in io_direction: xmin += buff
    if 'N' in io_direction: ymax -= buff
    if 'S' in io_direction: ymin += buff

    #ymin -= 15
    #xmax += 15

    # -------------------------
    # Step 3: Determine metal layers for power grid
    # -------------------------
    vdd_top = design_info["vdd_grid_top_layer"]
    vdd_bottom = design_info["vdd_grid_bottom_layer"]
    gnd_top = design_info["gnd_grid_top_layer"]
    gnd_bottom = design_info["gnd_grid_bottom_layer"]

    print(f"Using layers {vdd_bottom}?{vdd_top} for VDD mesh")
    print(f"Using layers {gnd_bottom}?{gnd_top} for GND mesh")

    vdd_top_num = int(layernames[vdd_top])
    vdd_bottom_num = int(layernames[vdd_bottom])
    gnd_top_num = int(layernames[gnd_top])
    gnd_bottom_num = int(layernames[gnd_bottom])

    vdd_metals = [(layernames[inverse_layers[i]], layers[inverse_layers[i]]['Draw'])
                  for i in range(vdd_top_num, vdd_bottom_num - 1, -1)]
    gnd_metals = [(layernames[inverse_layers[i]], layers[inverse_layers[i]]['Draw'])
                  for i in range(gnd_top_num, gnd_bottom_num - 1, -1)]

    # -------------------------
    # Step 4: Create final cell and reference original layout
    # -------------------------
    final_cell = gdspy.Cell(f"{top.name}_GRIDFILLED")
    final_cell.add(gdspy.CellReference(top))
    lib.add(final_cell)

    # -------------------------
    # Step 5: Flatten for bbox
    # -------------------------
    temp_flat_1 = final_cell.copy(name=f"{top.name}_TEMP_FLAT_1_FOR_BBOX")
    temp_flat_1.flatten()

    # ==========================================================
    # Step 6: Place DECAPS before power grid
    # ==========================================================
    print(">>> Performing DECAP placement before power grid...")
    obs_specs.append((39, 60))
    obs_fordecaps = obs_specs
    obs_fordecaps.append((38, 40))
    all_polys = temp_flat_1.get_polygons(by_spec=True)
    obs_polygons = []
    for spec in obs_fordecaps:
        obs_polygons.extend(all_polys.get(spec, []))
    #all_polys = temp_flat_1.get_polygons(by_spec=True)
    #obs_polygons = []
    #for spec in obs_fordecaps:
    #    polys = all_polys.get(spec, [])
    #    if not polys:
    #        continue

        # FIX FOR OCTAGON FRACTURE:
        # combine all fractured pieces into one convex polygon
    #    pts = np.vstack(polys)
    #    hull = convex_hull(pts)
    #    obs_polygons.append(hull)


    x_coords = np.arange(xmin + pitch_x, xmax, pitch_x)
    y_coords = np.arange(ymin + pitch_x, ymax, pitch_x)
    xx, yy = np.meshgrid(x_coords, y_coords)
    all_points = np.column_stack([xx.ravel(), yy.ravel()])
    candidate_points = filter_valid_points(all_points, obs_polygons, gap=int(pitch_x / 2)).tolist()

    decap_refs = place_decaps_from_grid_with_gds(
        all_points=candidate_points,
        obs_polygons=obs_polygons,
        decap_gds_path=os.path.join("FIXED_PRIMITIVES", "auto_gen_decap_lna_0_1.gds"),
        decap_cell_name="auto_gen_decap_lna_0_1",
        gap=10,
        xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
        num_decaps=None
    )

    decap_lib = gdspy.GdsLibrary()
    decap_lib.read_gds(os.path.join("FIXED_PRIMITIVES", "auto_gen_decap_lna_0_1.gds"))
    for c in decap_lib.cells.values():
        # Works fine: re-adding same cell names does not error if file matches prior definitions
        if c.name not in lib.cells:
            lib.add(c)

    for ref in decap_refs:
        final_cell.add(ref)

    # refresh flattened version after decaps
    temp_flat = final_cell.copy(name=f"{top.name}_TEMP_FLAT_FOR_BBOX")
    temp_flat.flatten()
    print(f"Placed {len(decap_refs)} DECAP instances before power grid generation.")
    # --- OBSTACLE EXTRACTION (from the temporary flattened cell) ---
    #VDD
    vdd_via_dict = {}

    for i, (l,d) in enumerate(vdd_metals):
        print(f"Adding metal {l}")
        if i % 2 == 0:
            direction = 'V'
        else:
            direction = 'H'
            print(i)
        obs_specs.append((l, d))
        #if obs_specs:
        #    all_polys = temp_flat.get_polygons(by_spec=True)
        #    obs_polygons = []
        #    for spec in obs_specs:
        #        polys = all_polys.get(spec, [])
        #        obs_polygons.extend(polys)
        #else:
        #    print("No obstacle specs provided, skipping obstacle avoidance.")
        all_polys = temp_flat.get_polygons(by_spec=True)
        obs_polygons = []
        for spec in [(l, d), (31, 0)]:
            polys = all_polys.get(spec, [])
            obs_polygons.extend(polys)
        if not obs_polygons:
            print(f"No obstacles found for layer {l}, datatype {d}")

        # --- FORMING GRID POINTS IN THE ENTIRE SPACE ---
        x_coords = np.arange(xmin + pitch_x, xmax, pitch_x)
        y_coords = np.arange(ymin + pitch_x, ymax, pitch_x)
        xx, yy = np.meshgrid(x_coords, y_coords)
        all_points = np.column_stack([xx.ravel(), yy.ravel()])

        # --- FILTER THEM USING OR LOGIC ---
        grid_points = filter_valid_points(all_points, obs_polygons, gap = max(pitch_x / 2, layerSpecs[inverse_layers[l]]['EndToEnd']/2, layerSpecs[inverse_layers[l]]['Pitch']/2)).tolist() #max(layerSpecs[inverse_layers[l]]['EndToEnd'], layerSpecs[inverse_layers[l]]['Pitch'])

        grid_points = [tuple(p) for p in grid_points]   # convert ndarray ? list of tuples
    

        # --- PERFORM MANHATTANT POWER GRID ROUTING ---
        final_cell, points = create_graph_manhattan_path(all_points = grid_points, layer=l, datatype=d, cell = final_cell,  line_width=poly_w, \
                                                connection_threshold = pitch_x, direction = direction)

        if l not in vdd_via_dict:
            vdd_via_dict[l] = points
        #lib.add(final_cell)
        # keep only the two newest keys
        if len(vdd_via_dict) > 2:
            oldest_key = next(iter(vdd_via_dict))
            del vdd_via_dict[oldest_key]
        if len(vdd_metals)>1: #Only if we have multiple layers for VDD
            if i > 0:
                required_via = None
                print(f"Adding VIA between Metal {l} and Metal {placed_metal}")
                if inverse_layers[l] == 'M1' and inverse_layers[placed_metal] == 'M2':
                    required_via = 'V1'
                if inverse_layers[l] == 'M2' and inverse_layers[placed_metal] == 'M3':
                    required_via = 'V2'
                if inverse_layers[l] == 'M3' and inverse_layers[placed_metal] == 'M4':
                    required_via = 'V3'
                if inverse_layers[l] == 'M4' and inverse_layers[placed_metal] == 'M5':
                    required_via = 'V4'
                if inverse_layers[l] == 'M8' and inverse_layers[placed_metal] == 'M9':
                    required_via = 'V8'
                if inverse_layers[l] == 'M7' and inverse_layers[placed_metal] == 'M8':
                    required_via = 'V7'
                if inverse_layers[l] == 'M6' and inverse_layers[placed_metal] == 'M7':
                    required_via = 'V6'
                if inverse_layers[l] == 'M5' and inverse_layers[placed_metal] == 'M6':
                    required_via = 'V5'
                #Adding via between metal layers
                via_cell, via_locs = place_vias_between_layers(
                    cell=final_cell,
                    vdd_via_dict=vdd_via_dict,
                    via_layer=layernames[required_via],
                    via_datatype=layers[required_via]['Draw'],
                    via_size=layerSpecs[required_via]['WidthX'],
                    via_name = required_via,
                    tol=0.5
                )
                #lib.add(via_cell)
            placed_metal = l

        #Add labels
        #add_edge_labels(cell=final_cell, text ='vdd', xmin=xmin, ymin=ymin,xmax=xmax, ymax=ymax, pitch=pitch_x, layer=labellayers[l][0], datatype=labellayers[l][1], direction=direction)
    #GND
    gnd_via_dict = {}
    obs_specs = [(31,0), (1001, 0)]
    print(f"GND mesh grid")
    for i, (l,d) in enumerate(gnd_metals):
        if i % 2 == 0:
            direction = 'H'
        else:
            direction = 'V'
            print(i)
        obs_specs.append((l, d))
        if obs_specs:
            all_polys = temp_flat.get_polygons(by_spec=True)
            obs_polygons = []
            for spec in obs_specs:
                polys = all_polys.get(spec, [])
                obs_polygons.extend(polys)
        else:
            print("No obstacle specs provided, skipping obstacle avoidance.")

        # --- FORMING GRID POINTS IN THE ENTIRE SPACE ---
        x_coords = np.arange(xmin + pitch_x, xmax, pitch_x)
        y_coords = np.arange(ymin + pitch_x, ymax, pitch_x)
        xx, yy = np.meshgrid(x_coords, y_coords)
        all_points = np.column_stack([xx.ravel(), yy.ravel()])

        # --- FILTER THEM USING OR LOGIC ---
        grid_points = filter_valid_points(all_points, obs_polygons, gap = max(pitch_x / 2, layerSpecs[inverse_layers[l]]['EndToEnd']/2, layerSpecs[inverse_layers[l]]['Pitch']/2)).tolist() #max(layerSpecs[inverse_layers[l]]['EndToEnd'], layerSpecs[inverse_layers[l]]['Pitch'])
        grid_points = [tuple(p) for p in grid_points]   # convert ndarray ? list of tuples
    
        #debug_draw_points(final_cell, all_points, layer=901)
        #debug_draw_points(final_cell, candidate_points, layer=902)
        #debug_draw_points(final_cell, grid_points, layer=903)


        # --- PERFORM MANHATTANT POWER GRID ROUTING ---
        final_cell, points  = create_graph_manhattan_path(all_points = grid_points, layer=l, datatype=d, cell = final_cell,  line_width=poly_w, \
                                                connection_threshold = pitch_x, direction = direction)
        #lib.add(final_cell)
        
        if l not in gnd_via_dict:
            gnd_via_dict[l] = points
        if len(gnd_via_dict) > 2:
            oldest_key = next(iter(gnd_via_dict))
            del gnd_via_dict[oldest_key]
        if len(gnd_metals)>1: #Only if we have multiple layers for GND
            if i > 0:
                required_via = None
                print(f"Adding VIA between Metal {l} and Metal {placed_metal}")
                if inverse_layers[l] == 'M1' and inverse_layers[placed_metal] == 'M2':
                    required_via = 'V1'
                if inverse_layers[l] == 'M2' and inverse_layers[placed_metal] == 'M3':
                    required_via = 'V2'
                if inverse_layers[l] == 'M3' and inverse_layers[placed_metal] == 'M4':
                    required_via = 'V3'
                if inverse_layers[l] == 'M4' and inverse_layers[placed_metal] == 'M5':
                    required_via = 'V4'
                if inverse_layers[l] == 'M8' and inverse_layers[placed_metal] == 'M9':
                    required_via = 'V8'
                if inverse_layers[l] == 'M7' and inverse_layers[placed_metal] == 'M8':
                    required_via = 'V7'
                if inverse_layers[l] == 'M6' and inverse_layers[placed_metal] == 'M7':
                    required_via = 'V6'
                if inverse_layers[l] == 'M5' and inverse_layers[placed_metal] == 'M6':
                    required_via = 'V5'
                #Adding via between metal layers
                via_cell, via_locs = place_vias_between_layers(
                    cell=final_cell,
                    vdd_via_dict=gnd_via_dict,
                    via_layer=layernames[required_via],
                    via_datatype=layers[required_via]['Draw'],
                    via_size=layerSpecs[required_via]['WidthX'],
                    via_name = required_via,
                    tol=0.5
                )
                #lib.add(via_cell)
            placed_metal = l
        #Add labels
        #add_edge_labels(cell=final_cell, text ='gnd', xmin=xmin, ymin=ymin,xmax=xmax, ymax=ymax, pitch=pitch_x, layer=labellayers[l][0], datatype=labellayers[l][1], direction=direction)

    lib.write_gds(args.outfile)
    print(f"Saved: {args.outfile}")


if __name__ == "__main__":
    main()


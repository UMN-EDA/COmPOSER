#!/usr/bin/env python3

import gdspy
import numpy as np
import argparse
import sys
import networkx as nx
import math
import json
import os
import gen_capacitor_layout as gen_cap


base = os.environ["PROJECT_HOME"]           # get the directory
pdk_file = os.path.join(base, "pdk", "rf_65_pdks", "65n_placer","layers.json")

#Reading layers.json file
def readLayerInfo(layerfile): 
    layers_specs_sacle = 1e3
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
                if "top_power_grid_layer" in layerdata["design_info"]:
                    design_info["top_power_grid_layer"] = layerdata["design_info"]["top_power_grid_layer"]
                if "bottom_power_grid_layer" in layerdata["design_info"]:
                    design_info["bottom_power_grid_layer"] = layerdata["design_info"]["bottom_power_grid_layer"]
    return (layers, layernames, labellayers, layerSpecs, design_info)






layers, layernames, labellayers, layerSpecs, design_info = readLayerInfo(pdk_file)
inverse_layers = {}
for k, v in layernames.items():
    if v not in inverse_layers:
        inverse_layers[v] = k
# print(inverse_layers)
# print("\n\n")
# print(layers)
# print("\n\n")
# print(layernames)
# print("\n\n")
# print(layerSpecs)
# print("\n\n")
# print(labellayers)
# print(design_info)


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
               move_for_symmetry=False, user_x_buffer=0, user_y_buffer=0, ignore_venc = False):
    # print(f"Inserting via {via_layer_num} : {via_layer_datatype} in rectangle {ll} : {ur}")

    vencA_H = layer_rules[via_name]['VencA_H'] #0.2 for VIA7
    vencP_H = layer_rules[via_name]['VencP_H'] #0.2 for VIA7
    if ignore_venc:
        vencA_H = 0
        vencP_H = 0
    via_size = layer_rules[via_name]['WidthX'] #0.36 for VIA7
    via_pitch = layer_rules[via_name]['SpaceX'] #0.54 for VIA7

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
            x += via_size + via_pitch
        final_y = y
        y += via_size + via_pitch

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
    # print(f"Placed {len(vias)} vias.")
    return cell

def filter_valid_points(points, obs_polygon, gap):
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
    for idx, (p_start, p_end) in enumerate(G.edges()):
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
            half = metal_width/2
            cell = insert_via(cell, (via_center[0] - half, via_center[1] - half), (via_center[0] + half, via_center[1] + half), layer_rules=layerSpecs, via_name= via_name, 
                              via_layer_num=layernames[via_name], via_layer_datatype=layers[via_name]['Draw'], move_for_symmetry=True, user_x_buffer=0, user_y_buffer=0, ignore_venc = False)
            vias_added.append((via_center[0], via_center[1], lower, upper))

    print(f"Placed {len(vias_added)} vias across {len(layer_keys) - 1} layer pairs.")
    return cell, vias_added

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
    label_offset = 1.0   # µm inward from chip edge for visibility

    if direction.upper() == 'H':
        # Labels along left and right edges for each horizontal gridline
        y_positions = np.arange(ymin, ymax, pitch)
        for y in y_positions:
            cell.add(gdspy.Label(text, position=(xmin + label_offset, y),
                                 layer=layer, texttype=datatype))
            cell.add(gdspy.Label(text, position=(xmax - label_offset, y),
                                 layer=layer, texttype=datatype))

    elif direction.upper() == 'V':
        # Labels along top and bottom edges for each vertical gridline
        x_positions = np.arange(xmin , xmax, pitch)
        for x in x_positions:
            cell.add(gdspy.Label(text, position=(x, ymin + label_offset),
                                 layer=layer, texttype=datatype))
            cell.add(gdspy.Label(text, position=(x, ymax - label_offset),
                                 layer=layer, texttype=datatype))

def place_decaps_from_grid_with_gds(all_points, obs_polygons, decap_gds_path, decap_cell_name,
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

def safe_add(lib, cell):
    """
    Add or overwrite a cell in a gdspy.GdsLibrary.
    If the cell already exists, it removes the old one first.
    """
    cname = cell.name
    if cname in lib.cells:
        # Explicitly remove old entry before adding new one
        del lib.cells[cname]
    lib.add(cell)

def main():
    # -------------------------
    # Step 1: Parse arguments
    # -------------------------
    parser = argparse.ArgumentParser(description="Place continuous parallel polygons in empty margin area around a layout")
    parser.add_argument("infile", help="Input GDS file")
    parser.add_argument("--top", help="Top cell name (optional)")
    parser.add_argument("-o", "--outfile", help="Output GDS file", default="output_with_grid.gds")
    args = parser.parse_args()

    obs_specs = [(31,0)]
    poly_w = 6
    pitch_x = 2 + poly_w

    # -------------------------
    # Step 2: Load GDS + get top cell
    # -------------------------
    lib = gdspy.GdsLibrary()
    lib.read_gds(args.infile)
    top = lib.cells[args.top] if args.top and args.top in lib.cells else lib.top_level()[0]
    bbox = top.get_bounding_box()
    io_height = 60
    io_direction = ['N', 'W']
    buff = io_height
    (xmin, ymin), (xmax, ymax) = bbox
    if 'E' in io_direction:
        xmax = xmax - buff
    if 'W' in io_direction:
        xmin = xmin + buff
    if 'N' in io_direction:
        ymax = ymax - buff
    if 'S' in io_direction:
        ymin = ymin + buff
        
    if 'E' not in io_direction:
        xmax = xmax + buff
    if 'W' not in io_direction:
        xmin = xmin - buff
    if 'N' not in io_direction:
        ymax = ymax + buff
    if 'S' not in io_direction:
        ymin = ymin - buff/2
        
    print(xmin, ymin, xmax, ymax)
    
    # xmin = xmin + 5
    ymin = ymin - pitch_x
    xmin = xmin + pitch_x
    ymax = ymax - pitch_x
    
    # xmax = xmax 
    # -------------------------
    # Step 3: Determine the metal information for VDD and GND mesh grid
    # -------------------------
    vdd_top = design_info["top_power_grid_layer"]
    vdd_bottom = design_info["bottom_power_grid_layer"]

    print(f"Using layers {vdd_bottom} to {vdd_top} for VDD mesh")

    vdd_top_num = int(layernames[vdd_top])
    vdd_bottom_num = int(layernames[vdd_bottom])

    
    vdd_metals = []
    if vdd_bottom_num != vdd_top_num:
        for i in range(vdd_top_num, vdd_bottom_num-1, -1):
            vdd_metals.append((layernames[inverse_layers[i]], layers[inverse_layers[i]]['Draw']))
    else:
        vdd_metals.append((layernames[vdd_top], layers[vdd_top]['Draw']))

    # -------------------------
    # Step 4: Create a new final cell and reference the original layout
    # -------------------------
    final_cell = gdspy.Cell(f"{top.name}_GRIDFILLED")
    final_cell.add(gdspy.CellReference(top))
    lib.add(final_cell)  # ONLY HERE
    # print(f"Created new top cell '{final_cell.name}' with reference to '{top.name}'.")
    # -------------------------
    # Step 5: Get layout bounding box from a temporary flattened version
    # -------------------------
    temp_flat_1 = final_cell.copy(name=f"{top.name}_TEMP_FLAT_1_FOR_BBOX")
    temp_flat_1.flatten()
    # Always create an obstacle cell, even if empty
    #obstacle_cell = gdspy.Cell("PG")
    # ==========================================
    # Step X: Insert Decaps in Empty Regions
    # ==========================================
    xmin = xmin + 1 * pitch_x
    xmax = xmax
    x_step = 1 * pitch_x
    ymin = ymin + 1 * pitch_x
    ymax = ymax
    y_step = 1 * pitch_x
    x_coords = np.arange(xmin, xmax, x_step)
    y_coords = np.arange(ymin, ymax, y_step)
    xx, yy = np.meshgrid(x_coords, y_coords)
    
    all_points = np.column_stack([xx.ravel(), yy.ravel()])
    
    obs_specs.append((39, 60))
    if obs_specs:
        all_polys = temp_flat_1.get_polygons(by_spec=True)
        obs_polygons = []
        for spec in obs_specs:
            polys = all_polys.get(spec, [])
            obs_polygons.extend(polys)

    # --- FILTER THEM USING OR LOGIC ---
    grid_points = filter_valid_points(all_points, obs_polygons, gap = int(pitch_x / 2)).tolist() #max(layerSpecs[inverse_layers[l]]['EndToEnd'], layerSpecs[inverse_layers[l]]['Pitch'])

    grid_points = [tuple(p) for p in grid_points]   # convert ndarray ? list of tuples
    gap = 10


    # Use the latest grid_points as candidate decap positions
    candidate_points = grid_points  # reuse from your last mesh iteration
    chip_w = xmax - xmin
    chip_h = ymax - ymin

    decap_refs = place_decaps_from_grid_with_gds(
        all_points=candidate_points,
        obs_polygons=obs_polygons,
        decap_gds_path=os.path.join(base, "DEV", "FIXED_PRIMITIVES", "auto_gen_decap_lna_0_1.gds"),
        decap_cell_name="auto_gen_decap_lna_0_1",
        gap=gap,
        xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
        num_decaps=None
    )
    # --- FIX 1: Load the same decap GDS into this main library ---
    decap_lib = gdspy.GdsLibrary()
    decap_lib.read_gds(os.path.join(base, "DEV", "FIXED_PRIMITIVES", "auto_gen_decap_lna_0_1.gds"))

    for c in decap_lib.cells.values():
        lib.add(c)

    # --- FIX 2: Add references to the final cell ---
    for ref in decap_refs:
        final_cell.add(ref)
    
    
    temp_flat = final_cell.copy(name=f"{top.name}_TEMP_FLAT_FOR_BBOX")
    temp_flat.flatten()
    
    
    

    # print(f"Layout bounding box: ({xmin}, {ymin}) to ({xmax}, {ymax})")

    # --- OBSTACLE EXTRACTION (from the temporary flattened cell) ---
    #VDD
    step_x =1 
    step_y =1 
    vdd_via_dict = {}
    gnd_via_dict = {}
    decaps_placed = False
    print(f"Metals used for power grid: {vdd_metals}")
    for i, (l,d) in enumerate(vdd_metals):
        print(f"Adding metal {l}")
        if i % 2 == 0:
            direction = 'H'
            step_y = 2
            step_x = 1
            start_y = 0
            start_x = 0
        else:
            direction = 'V'
            step_y = 1
            step_x = 2
            start_x = 0
            start_y = -1
        
        obs_specs[-1] = (l, d)
        if obs_specs:
            all_polys = temp_flat.get_polygons(by_spec=True)
            obs_polygons = []
            for spec in obs_specs:
                polys = all_polys.get(spec, [])
                obs_polygons.extend(polys)
        else:
            print("No obstacle specs provided, skipping obstacle avoidance.")

        # --- FORMING GRID POINTS IN THE ENTIRE SPACE ---
        text = 'vdd'
        for j in range(2):

            if j == 1 :
                text = 'gnd'
                if direction == 'H':
                    start_y = 1
                    start_x = 0
                else:
                    start_x = 1
                    start_y = 0


            xmin = xmin + start_x * pitch_x
            xmax = xmax
            x_step = step_x * pitch_x
            ymin = ymin + start_y * pitch_x
            ymax = ymax
            y_step = step_y * pitch_x
            x_coords = np.arange(xmin, xmax, x_step)
            y_coords = np.arange(ymin, ymax, y_step)
            xx, yy = np.meshgrid(x_coords, y_coords)
            
            all_points = np.column_stack([xx.ravel(), yy.ravel()])

            # --- FILTER THEM USING OR LOGIC ---
            grid_points = filter_valid_points(all_points, obs_polygons, gap = max(pitch_x / 2, layerSpecs[inverse_layers[l]]['EndToEnd']/2, layerSpecs[inverse_layers[l]]['Pitch']/2)).tolist() #max(layerSpecs[inverse_layers[l]]['EndToEnd'], layerSpecs[inverse_layers[l]]['Pitch'])

            


            grid_points = [tuple(p) for p in grid_points]   # convert ndarray ? list of tuples
        
           
            # --- PERFORM MANHATTANT POWER GRID ROUTING ---
            final_cell, points = create_graph_manhattan_path(all_points = grid_points, layer=l, datatype=d, cell = final_cell,  line_width=poly_w, \
                                                    connection_threshold = pitch_x, direction = direction)
            #lib.add(final_cell)
            if j == 0: #For VDD
                if l not in vdd_via_dict:
                    vdd_via_dict[l] = points
            if j == 1: #For GND
                if l not in gnd_via_dict:
                    gnd_via_dict[l] = points
            
            #Add labels
            step = max(y_step, x_step)
            #add_edge_labels(cell=final_cell, text =text, xmin=xmin, ymin=ymin,xmax=xmax, ymax=ymax, pitch=step , layer=labellayers[l][0], datatype=labellayers[l][1], direction=direction)
        # keep only the two newest keys
        if len(vdd_via_dict) > 2:
            oldest_key = next(iter(vdd_via_dict))
            del vdd_via_dict[oldest_key]
        # keep only the two newest keys
        if len(gnd_via_dict) > 2:
            oldest_key = next(iter(gnd_via_dict))
            del gnd_via_dict[oldest_key]
        if len(gnd_via_dict)>1: #Only if we have multiple layers for VDD
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
                    tol=0.5,
                    metal_width = poly_w
                )
                #lib.add(via_cell)
                via_cell, via_locs = place_vias_between_layers(
                    cell=final_cell,
                    vdd_via_dict=gnd_via_dict,
                    via_layer=layernames[required_via],
                    via_datatype=layers[required_via]['Draw'],
                    via_size=layerSpecs[required_via]['WidthX'],
                    via_name = required_via,
                    tol=0.5,
                    metal_width = poly_w
                )
                #lib.add(via_cell)
        placed_metal = l

    

    lib.write_gds(args.outfile)
    print(f"Saved: {args.outfile}")

    
    #obstacle_cell.add(final_cell)  
    # obstacle_cell.add(bbox_rect)  
    # Define a new output filename for the obstacles GDS
    #obstacle_outfile = args.outfile.replace(".gds", "_obstacles.gds")
    
    # Write the obstacle cell to its own GDS file
    #gdspy.write_gds("PG.gds", cells=[obstacle_cell])
    #print(f"Saved obstacles-only layout to: PG.gds")

if __name__ == "__main__":
    main()


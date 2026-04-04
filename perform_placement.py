import os, json, math, logging
from gurobipy import Model, GRB, quicksum
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import sys
import plotly.graph_objects as go
import argparse
import os
import sys
import utils.gen_placement_gds as gen_placement_gds

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)



def load_config(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
    return cfg


# =========================
# Data structures
# =========================
class Module:
    def __init__(self, name, variants=None, fixed=None, w=None, h=None, pins=None, pad_only=False, pad_sides=None):
        self._name = name
        self.variants = []
        self.fixed = fixed
        self.pad_only = pad_only
        self.pad_sides = pad_sides or []

        # normalize pins to float
        self.pins = [(float(p["x"]), float(p["y"])) for p in (pins or [])]

        if variants:
            for v in variants:
                x0, y0 = v["ll"]; x1, y1 = v["ur"]
                W, H = x1 - x0, y1 - y0
                vpins = [(float(p["x"]), float(p["y"])) for p in v.get("pins", [])]
                self.variants.append({"w": W, "h": H, "pins": vpins,"gds_file": v.get("gds_file"), "dummy_gds_file": v.get("dummy_gds_file")})
                
        elif w and h:
            self.variants.append({"w": float(w), "h": float(h), "pins": self.pins, "gds_file": None, "dummy_gds_file": None})
        elif fixed:
            x0, y0 = fixed["ll"]; x1, y1 = fixed["ur"]
            W, H = x1 - x0, y1 - y0
            fpins = [(float(p["x"]), float(p["y"])) for p in fixed.get("pins", [])]
            self.variants.append({"w": W, "h": H, "pins": fpins, "gds_file": fixed.get("gds_file"),  "dummy_gds_file": fixed.get("dummy_gds_file")})

        else:
            raise ValueError(f"Module {name} has no valid size info")



    def __repr__(self):
        return f"Module({self._name}, variants={len(self.variants)}, fixed={self.fixed is not None})"
def rotate_pin(px0, py0, vw, vh, ori):
    """
    Rotate a pin (px0, py0) inside a rectangle of size (vw, vh)
    by ori * 90 degrees CCW around the lower-left corner (0,0).
    ori = 0 ? R0, ori = 1 ? R90, ori = 2 ? R180, ori = 3 ? R270
    """
    if ori == 0:      # R0
        return px0, py0
    elif ori == 1:    # R90 CCW
        return py0, vw - px0
    elif ori == 2:    # R180
        return vw - px0, vh - py0
    elif ori == 3:    # R270 CCW
        return vh - py0, px0
    else:
        raise ValueError(f"Invalid orientation {ori}")


class Constraints:
    def __init__(self, data):
        self.halo = data.get("halo", 0)                 #Halo gap around each modules
        self.keepouts = data.get("keepouts", [])        #Keepout regions - regions where no modules can be placed
        self.symmetry = data.get("symmetry", [])        #Symmetry accross a given axes
        self.alignment = data.get("alignment", [])      #Align along a certain axes
        self.regions = data.get("regions", {})          #Region specific to a given module, where that module has to be placed
        self.proximity = data.get("proximity", [])      #Proximity within which a pair of modules has to be placed
        self.ordering = data.get("ordering", [])        #Ordering of modules in a particular order
    @classmethod
    def from_json(cls, json_file):
        with open(json_file, "r") as f:
            data = json.load(f)
        return cls(data)

    def apply_halo(self, model, x, y, w, h, M, t, i, j):
        #"halo": 3000
        """Add halo-aware non-overlap constraint between module i and j."""
        halo = self.halo
        model.addConstr(x[i] + w[i] + halo <= x[j]  + M*(1 - t[0]))
        model.addConstr(x[j] + w[j] + halo <= x[i]  + M*(1 - t[1]))
        model.addConstr(y[i] + h[i] + halo <= y[j]  + M*(1 - t[2]))
        model.addConstr(y[j] + h[j] + halo <= y[i]  + M*(1 - t[3]))


    def apply_keepouts(self, model, mod_name, xi, yi, wi, hi, M):
        #{        
        #   "keepouts": [
        #     {"ll": [0, 0], "ur": [100, 200]},
        #     {"ll": [300, 50], "ur": [450, 150]}
        #   ]
        #}
        """Ensure module does not overlap with keepout regions."""
        for k, ko in enumerate(self.keepouts):
            x0, y0 = ko["ll"]; x1, y1 = ko["ur"]

            b = model.addVars(4, vtype=GRB.BINARY, name=f"keepout_{mod_name}_{k}")
            model.addConstr(b.sum() == 1)
            # Left
            model.addConstr(xi + wi <= x0 + M*(1 - b[0]))
            # Right
            model.addConstr(xi >= x1 - M*(1 - b[1]))
            # Below
            model.addConstr(yi + hi <= y0 + M*(1 - b[2]))
            # Above
            model.addConstr(yi >= y1 - M*(1 - b[3]))

    def apply_regions(self, model, mod_name, xi, yi, wi, hi):
        """Restrict module inside its allowed region if defined."""
        #{
        #  "regions": {
        #    "M1": {"ll": [0, 0], "ur": [200, 200]},
        #    "M2": {"ll": [300, 100], "ur": [500, 400]}
        #  }
        #}
        if mod_name in self.regions:
            r = self.regions[mod_name]
            model.addConstr(xi >= r["ll"][0])
            model.addConstr(yi >= r["ll"][1])
            model.addConstr(xi + wi <= r["ur"][0])
            model.addConstr(yi + hi <= r["ur"][1])

    def apply_symmetry(self, model, mod_index, x, y, w, h):
        """
        Apply symmetry constraints across an axis.

        Supported formats:

        1) Ordered module list:
           {
             "modules": ["L2", "L1", "C", "R1", "R2"],
             "type": "vertical",
             "axis_x": 500
           }

           Pairing is done from the outside in:
           (L2,R2), (L1,R1), and if odd count, the middle module is centered on the axis.

        2) Explicit pairs:
           {
             "pairs": [["L2", "R2"], ["L1", "R1"]],
             "self_symmetric": ["C"],
             "type": "vertical",
             "axis_x": 500
           }
        """
        for s_idx, s in enumerate(self.symmetry):
            stype = s["type"].lower()

            if stype == "vertical":
                if "axis_x" not in s:
                    raise ValueError(f"symmetry[{s_idx}] with type='vertical' requires 'axis_x'")
                axis = s["axis_x"]
            elif stype == "horizontal":
                if "axis_y" not in s:
                    raise ValueError(f"symmetry[{s_idx}] with type='horizontal' requires 'axis_y'")
                axis = s["axis_y"]
            else:
                raise ValueError(f"symmetry[{s_idx}] has invalid type '{s['type']}'")

            pair_list = []
            self_list = []

            if "pairs" in s:
                for p_idx, pair in enumerate(s["pairs"]):
                    if len(pair) != 2:
                        raise ValueError(
                            f"symmetry[{s_idx}]['pairs'][{p_idx}] must contain exactly 2 module names"
                        )
                    a, b = pair
                    if a not in mod_index or b not in mod_index:
                        raise ValueError(
                            f"Unknown module in symmetry[{s_idx}]['pairs'][{p_idx}]: {pair}"
                        )
                    pair_list.append((a, b))

                for mname in s.get("self_symmetric", []):
                    if mname not in mod_index:
                        raise ValueError(
                            f"Unknown module in symmetry[{s_idx}]['self_symmetric']: {mname}"
                        )
                    self_list.append(mname)

            else:
                mods = s.get("modules", [])
                if len(mods) < 2:
                    raise ValueError(
                        f"symmetry[{s_idx}] needs either 'pairs' or at least 2 names in 'modules'"
                    )

                for mname in mods:
                    if mname not in mod_index:
                        raise ValueError(f"Unknown module '{mname}' in symmetry[{s_idx}]")

                left = 0
                right = len(mods) - 1
                while left < right:
                    pair_list.append((mods[left], mods[right]))
                    left += 1
                    right -= 1

                if left == right:
                    self_list.append(mods[left])

            # Apply pair symmetry
            for p_idx, (ma, mb) in enumerate(pair_list):
                i = mod_index[ma]
                j = mod_index[mb]

                if stype == "vertical":
                    model.addConstr(
                        x[i] + w[i] / 2 + x[j] + w[j] / 2 == 2 * axis,
                        name=f"sym_v_{s_idx}_{p_idx}_{ma}_{mb}"
                    )
                else:
                    model.addConstr(
                        y[i] + h[i] / 2 + y[j] + h[j] / 2 == 2 * axis,
                        name=f"sym_h_{s_idx}_{p_idx}_{ma}_{mb}"
                    )

            # Apply self-symmetry for center modules
            for c_idx, mname in enumerate(self_list):
                i = mod_index[mname]

                if stype == "vertical":
                    model.addConstr(
                        x[i] + w[i] / 2 == axis,
                        name=f"sym_v_self_{s_idx}_{c_idx}_{mname}"
                    )
                else:
                    model.addConstr(
                        y[i] + h[i] / 2 == axis,
                        name=f"sym_h_self_{s_idx}_{c_idx}_{mname}"
                    )


    def apply_alignment(self, model, mod_index, x, y, w, h):
        """
        Align any number of modules.

        Supported types:
          top, bottom, left, right,
          center_x, center_y
        """
        for a_idx, a in enumerate(self.alignment):
            mods = a.get("modules", [])
            atype = a["type"].lower()

            if len(mods) < 2:
                raise ValueError(
                    f"alignment[{a_idx}] must contain at least 2 module names"
                )

            for mname in mods:
                if mname not in mod_index:
                    raise ValueError(f"Unknown module '{mname}' in alignment[{a_idx}]")

            ref_name = mods[0]
            r = mod_index[ref_name]

            for k in range(1, len(mods)):
                mname = mods[k]
                i = mod_index[mname]

                if atype == "top":
                    model.addConstr(
                        y[i] + h[i] == y[r] + h[r],
                        name=f"align_top_{a_idx}_{ref_name}_{mname}"
                    )

                elif atype == "bottom":
                    model.addConstr(
                        y[i] == y[r],
                        name=f"align_bottom_{a_idx}_{ref_name}_{mname}"
                    )

                elif atype == "left":
                    model.addConstr(
                        x[i] == x[r],
                        name=f"align_left_{a_idx}_{ref_name}_{mname}"
                    )

                elif atype == "right":
                    model.addConstr(
                        x[i] + w[i] == x[r] + w[r],
                        name=f"align_right_{a_idx}_{ref_name}_{mname}"
                    )

                elif atype == "center_x":
                    model.addConstr(
                        x[i] + w[i] / 2 == x[r] + w[r] / 2,
                        name=f"align_cx_{a_idx}_{ref_name}_{mname}"
                    )

                elif atype == "center_y":
                    model.addConstr(
                        y[i] + h[i] / 2 == y[r] + h[r] / 2,
                        name=f"align_cy_{a_idx}_{ref_name}_{mname}"
                    )

                else:
                    raise ValueError(
                        f"alignment[{a_idx}] has invalid type '{a['type']}'"
                    )

    def apply_proximity(self, model, mod_index, x, y, w, h):
        """
        Linear convex proximity.

        Supported formats:
          {"modules": ["A", "B"], "max_dx": 100, "max_dy": 80}
          {"modules": ["A", "B"], "max_dist": 120}   # convex quadratic circle
        """
        for p_idx, p in enumerate(self.proximity):
            mods = p.get("modules", [])
            if len(mods) != 2:
                raise ValueError(
                    f"proximity[{p_idx}] must contain exactly 2 module names"
                )

            a, b = mods
            if a not in mod_index or b not in mod_index:
                raise ValueError(
                    f"Unknown module in proximity[{p_idx}]: {mods}"
                )

            if p.get("min_dist", None) is not None:
                raise ValueError(
                    f"proximity[{p_idx}] uses min_dist, which is non-convex."
                )

            i = mod_index[a]
            j = mod_index[b]

            cx_i = x[i] + w[i] / 2
            cy_i = y[i] + h[i] / 2
            cx_j = x[j] + w[j] / 2
            cy_j = y[j] + h[j] / 2

            dx = cx_i - cx_j
            dy = cy_i - cy_j

            if "max_dx" in p:
                d = float(p["max_dx"])
                model.addConstr(dx <= d,  name=f"prox_dx_pos_{p_idx}_{a}_{b}")
                model.addConstr(dx >= -d, name=f"prox_dx_neg_{p_idx}_{a}_{b}")

            if "max_dy" in p:
                d = float(p["max_dy"])
                model.addConstr(dy <= d,  name=f"prox_dy_pos_{p_idx}_{a}_{b}")
                model.addConstr(dy >= -d, name=f"prox_dy_neg_{p_idx}_{a}_{b}")

            if "max_dist" in p:
                d = float(p["max_dist"])
                model.addQConstr(
                    dx * dx + dy * dy <= d * d,
                    name=f"prox_max_{p_idx}_{a}_{b}"
                )
    def apply_ordering(self, model, mod_index, x, y, w, h):
        """Apply ordering constraints between one or more modules."""
        #{
        #  "ordering": [
        #    {"modules": ["A", "B"], "type": "horizontal", "gap": 10},
        #    {"modules": ["GND0", "INPUT", "GND1"], "type": "vertical", "gap": 5}
        #  ]
        #}
        if not hasattr(self, "ordering") or not self.ordering:
            return

        for o in self.ordering:
            mods = o["modules"]
            gap = o.get("gap", 0)
            otype = o["type"].lower()

            # Apply pairwise ordering along the chain
            for k in range(len(mods) - 1):
                i, j = mod_index[mods[k]], mod_index[mods[k + 1]]

                if otype == "horizontal":
                    # enforce left-to-right order
                    model.addConstr(x[i] + w[i] + gap <= x[j],
                                    name=f"order_h_{mods[k]}_{mods[k+1]}")

                elif otype == "vertical":
                    # enforce bottom-to-top order
                    model.addConstr(y[i] + h[i] + gap <= y[j],
                                    name=f"order_v_{mods[k]}_{mods[k+1]}")



def load_design(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)
    modules = {}
    for name, entry in data["modules"].items():
        m = Module(
            name,
            variants=entry.get("variants"),
            fixed=entry.get("fixed"),
            w=entry.get("w"),
            h=entry.get("h"),
            pins=entry.get("pins"),
            pad_only=entry.get("pad_only", False),
            pad_sides=entry.get("pad_sides", [])
        )
        modules[name] = m
    return data.get("chip", {}), modules, data.get("nets", {})

def load_constraints(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)
    return Constraints(data)

def compute_pin_position(idx, ep, x, y, z_map, ori, mod_list):

    xi, yi = x[idx], y[idx]

    if idx in z_map:  # multi-variant
        px_expr, py_expr = 0, 0
        for j, vj in enumerate(mod_list[idx].variants):
            vw, vh = vj["w"], vj["h"]

            if "pin_index" in ep and vj.get("pins"):
                k = int(ep["pin_index"])
                px0, py0 = vj["pins"][k]
            else:
                px0, py0 = vw/2, vh/2

            # R0
            px_expr += z_map[idx][(j,0)] * px0
            py_expr += z_map[idx][(j,0)] * py0
            # R90
            px_expr += z_map[idx][(j,1)] * py0
            py_expr += z_map[idx][(j,1)] * (vw - px0)
            # R180
            px_expr += z_map[idx][(j,2)] * (vw - px0)
            py_expr += z_map[idx][(j,2)] * (vh - py0)
            # R270
            px_expr += z_map[idx][(j,3)] * (vh - py0)
            py_expr += z_map[idx][(j,3)] * px0

        return xi + px_expr, yi + py_expr

    else:  # single variant
        vj = mod_list[idx].variants[0]
        vw, vh = vj["w"], vj["h"]

        if "pin_index" in ep and vj.get("pins"):
            k = int(ep["pin_index"])
            px0, py0 = vj["pins"][k]
        else:
            px0, py0 = vw/2, vh/2

        b0 = ori[idx].get(0, 0)
        b1 = ori[idx].get(1, 0)
        b2 = ori[idx].get(2, 0)
        b3 = ori[idx].get(3, 0)

        px_expr = b0*px0 + b1*py0 + b2*(vw - px0) + b3*(vh - py0)
        py_expr = b0*py0 + b1*(vw - px0) + b2*(vh - py0) + b3*px0

        return xi + px_expr, yi + py_expr

def resolve_endpoint(name, endpoints):
    """
    name: 'module/pin_name' (e.g. 'bias_mos/D')
    endpoints: list of endpoint dicts with keys:
        - module
        - pin_name or pin
        - pin_index
    """
    mod, pin = name.split("/")

    for ep in endpoints:
        # Prefer pin_name, then pin, then synthetic name from pin_index
        ep_pin = ep.get("pin_name")
        if ep_pin is None:
            ep_pin = ep.get("pin")
        if ep_pin is None:
            ep_pin = f"p{ep.get('pin_index', 0)}"

        if ep["module"] == mod and ep_pin == pin:
            return ep

    raise ValueError(f"Endpoint {name} not found in net endpoints")


def ilp_callback_old(model, where):
    """
    Capture intermediate feasible placement states during ILP solving.
    Saves module coordinates to JSON files whenever a new integer solution is found.
    """

    if where == GRB.Callback.MIPSOL:
        os.makedirs("snapshots", exist_ok=True)

        try:
            snapshot = {}

            # Collect x/y coordinates for each module
            for m in model._modules:
                if hasattr(m, "x_var") and hasattr(m, "y_var"):
                    x = model.cbGetSolution(m.x_var)
                    y = model.cbGetSolution(m.y_var)
                    w = m.variants[0]["w"]
                    h = m.variants[0]["h"]
                    snapshot[m._name] = {"x": x, "y": y, "w": w, "h": h}
                else:
                    print(f"[Warning] Module {m._name} missing x_var/y_var, skipping")

            # Save snapshot as JSON
            idx = len(model._snapshots)
            out_file = f"snapshots/placement_step_{idx:03d}.json"
            with open(out_file, "w") as f:
                json.dump(snapshot, f, indent=2)

            model._snapshots.append(snapshot)
            obj = model.cbGet(GRB.Callback.MIPSOL_OBJ)
            print(f"[Callback] Saved placement snapshot {idx:03d} | Objective = {obj:.2f}")

        except Exception as e:
            print(f"[Callback Error] {e}")




def ilp_callback(model, where):
    """
    Capture intermediate feasible placement states during ILP solving,
    now correctly determining module width/height based on the selected
    orientation/variant variables from the MIPSOL solution.
    """

    if where == GRB.Callback.MIPSOL:
        os.makedirs("snapshots", exist_ok=True)

        try:
            snapshot = {}

            # Collect x/y coordinates and actual w/h for each module
            for i, m in enumerate(model._modules):
                mname = m._name
                
                # Ensure the core position variables exist
                if not (hasattr(m, "x_var") and hasattr(m, "y_var")):
                    print(f"[Warning] Module {mname} missing x_var/y_var, skipping")
                    continue
                
                # 1. Get position solution
                x = model.cbGetSolution(m.x_var)
                y = model.cbGetSolution(m.y_var)
                
                w_disp, h_disp = 0.0, 0.0
                orientation_label = "N/A"

                # Check if multi-variant (variant selection variables 'z' exist)
                # The 'z_map' is implicitly created in the main function's scope, 
                # but we must rely on accessing the actual model variables.
                
                if len(m.variants) > 1:
                    # Multi-variant case: Use the z variables (z_map)
                    
                    # We must re-create the check for the active z variable since 
                    # the z_map is not stashed on the model object in the provided code.
                    # A robust solution needs access to the 'z' vars, which are indexed
                    # by (variant_idx, rotation_idx). We will use the stored GRB Vars:
                    
                    selected_j, selected_r = -1, -1
                    
                    for j in range(len(m.variants)):
                        for r in range(4):
                            # Variable name pattern: z_{m._name}_{j}_{r}
                            var_name = f"z_{mname}_{j}_{r}"
                            
                            try:
                                z_var = model.getVarByName(var_name)
                                if z_var and model.cbGetSolution(z_var) > 0.5:
                                    selected_j, selected_r = j, r
                                    break
                            except:
                                # Handle case where var might not exist if logic changed
                                pass 
                        if selected_j != -1:
                            break
                            
                    if selected_j != -1:
                        w0 = m.variants[selected_j]["w"]
                        h0 = m.variants[selected_j]["h"]
                        
                        # Apply rotation logic: swap for R90 (1) and R270 (3)
                        if selected_r in [1, 3]:
                            w_disp, h_disp = h0, w0
                        else: # R0 (0) and R180 (2)
                            w_disp, h_disp = w0, h0
                            
                        orientation_label = f"V{selected_j}R{selected_r}"
                    
                else:
                    # Single-variant case: Use the 'ori' variables
                    v = m.variants[0]
                    w0, h0 = v["w"], v["h"]
                    
                    selected_r = -1
                    # Access the orientation variables: ori[i][r]
                    for r in range(4):
                        # Variable name pattern: ori_{m._name}_{r}
                        var_name = f"ori_{mname}_{r}"
                        
                        try:
                            ori_var = model.getVarByName(var_name)
                            if ori_var and model.cbGetSolution(ori_var) > 0.5:
                                selected_r = r
                                break
                        except:
                            # Skip if the orientation variable doesn't exist (e.g., for pad_only)
                            pass
                            
                    if selected_r != -1:
                        # Apply rotation logic: swap for R90 (1) and R270 (3)
                        if selected_r in [1, 3]:
                            w_disp, h_disp = h0, w0
                        else: # R0 (0) and R180 (2)
                            w_disp, h_disp = w0, h0
                            
                        orientation_label = f"R{selected_r}"
                    else:
                        # Fallback for modules with no rotation variable (shouldn't happen here)
                        w_disp, h_disp = w0, h0
                        orientation_label = "R0 (Fallback)"

                # 2. Save snapshot with correct dimensions and orientation info
                snapshot[mname] = {
                    "x": x, 
                    "y": y, 
                    "w": w_disp, 
                    "h": h_disp,
                    "orientation": orientation_label 
                }

            # Save snapshot as JSON
            idx = len(model._snapshots)
            out_file = f"snapshots/placement_step_{idx:03d}.json"
            with open(out_file, "w") as f:
                json.dump(snapshot, f, indent=2)

            model._snapshots.append(snapshot)
            obj = model.cbGet(GRB.Callback.MIPSOL_OBJ)
            print(f"[Callback] Saved placement snapshot {idx:03d} | Objective = {obj:.2f}")

        except Exception as e:
            print(f"[Callback Error] {e}")
# =========================
# ILP Floorplanner
# =========================
def gurobi_floorplan(chip, modules, nets, constraints, aspect_ratio=None, margin=0.01, timelimit=20, level = 1, weight_hpwl = 1):
    model = Model("ILP_Floorplan")
    model.setParam("OutputFlag", 1)
    model.setParam("TimeLimit", timelimit)

    io_height = chip.get("io_h", 10000) + 15000 #We add 15um to maintain a regular gap between IO Blocks and internal modules for power grid routing
    io_pitch  = chip.get("io_pitch", 10000)

    pad_mode = chip.get("pad_mode", chip.get("io_mode", "periphery")).lower()
    if pad_mode not in ("periphery", "bga"):
        raise ValueError(f"Unsupported pad_mode '{pad_mode}'. Use 'periphery' or 'bga'.")

    bga_pitch_x = chip.get("bga_pitch_x", chip.get("pitchx", chip.get("pad_pitch_x")))
    bga_pitch_y = chip.get("bga_pitch_y", chip.get("pitchy", chip.get("pad_pitch_y")))
    bga_origin_x = float(chip.get("bga_origin_x", 0.0))
    bga_origin_y = float(chip.get("bga_origin_y", 0.0))

    if pad_mode == "bga":
        if bga_pitch_x is None or bga_pitch_y is None:
            raise ValueError("BGA pad mode requires chip['bga_pitch_x'] and chip['bga_pitch_y'] (or pitchx/pitchy aliases).")
        bga_pitch_x = float(bga_pitch_x)
        bga_pitch_y = float(bga_pitch_y)
        if bga_pitch_x <= 0 or bga_pitch_y <= 0:
            raise ValueError("BGA pitches must be positive.")

    mod_list  = list(modules.values()) if isinstance(modules, dict) else modules
    mod_index = {m._name: i for i, m in enumerate(mod_list)}

    Mx = sum(max(v["w"] for v in m.variants) for m in mod_list)
    My = sum(max(v["h"] for v in m.variants) for m in mod_list)
    M  = max(Mx, My)
    # Your requested mapping: WEST -> 90deg (R90 = 1)
    # R0=0, R90=1, R180=2, R270=3
    side_to_ori = {"N": 0, "E": 1, "S": 2, "W": 3}

    x, y, w, h, ori = {}, {}, {}, {}, {}
    for i, m in enumerate(mod_list):
        x[i] = model.addVar(lb=0, ub=Mx, name=f"x_{m._name}")
        y[i] = model.addVar(lb=0, ub=My, name=f"y_{m._name}")
        w[i] = model.addVar(lb=0, ub=Mx, name=f"w_{m._name}")
        h[i] = model.addVar(lb=0, ub=My, name=f"h_{m._name}")

        # Attach Gurobi variable handles to Module object
        m.x_var = x[i]
        m.y_var = y[i]
        m.w_var = w[i]
        m.h_var = h[i]
        # Orientation variables
        ori[i] = {}
        if m.pad_only and pad_mode == "periphery":
            allowed_sides = m.pad_sides or ["N", "S", "E", "W"]
            for s in allowed_sides:
                r = side_to_ori[s]
                ori[i][r] = model.addVar(vtype=GRB.BINARY, name=f"ori_{m._name}_{r}")
        else:
            for r in range(4):
                ori[i][r] = model.addVar(vtype=GRB.BINARY, name=f"ori_{m._name}_{r}")

        model.addConstr(quicksum(ori[i].values()) == 1)
        model.addConstr(x[i] >= 0)
        model.addConstr(y[i] >= 0)

    # Chip outline
    W = model.addVar(lb=0, ub=Mx, name="W")
    H = model.addVar(lb=0, ub=My, name="H")

    # Chip size bounds
    for i in range(len(mod_list)):
        model.addConstr(W >= x[i] + w[i])
        model.addConstr(H >= y[i] + h[i])

    # Aspect ratio
    if aspect_ratio:
        model.addConstr(W >= (aspect_ratio - margin) * H)
        model.addConstr(W <= (aspect_ratio + margin) * H)

    # ======================
    # Pad placement
    #   periphery : existing edge-based IO rows / columns
    #   bga       : snap pad centers to an internal X/Y grid
    # ======================
    for i, m in enumerate(mod_list):

        if not m.pad_only:
            continue

        if pad_mode == "periphery":
            allowed_sides = m.pad_sides or ["N", "S", "E", "W"]

            # one-hot side choice
            side_bin = {s: model.addVar(vtype=GRB.BINARY, name=f"{m._name}_side_{s}") for s in allowed_sides}
            model.addConstr(quicksum(side_bin[s] for s in allowed_sides) == 1)

            for s in allowed_sides:
                r = side_to_ori[s]
                # Link side choice to orientation
                model.addConstr(ori[i][r] == side_bin[s])

                if s == "N":
                    # y+h == H
                    model.addConstr(y[i] + h[i] >= H - (1 - side_bin[s]) * M)
                    model.addConstr(y[i] + h[i] <= H + (1 - side_bin[s]) * M)

                    kN = model.addVar(vtype=GRB.INTEGER, name=f"{m._name}_slotN")
                    model.addConstr(x[i] - kN * io_pitch <= (1 - side_bin[s]) * M)
                    model.addConstr(x[i] - kN * io_pitch >= -(1 - side_bin[s]) * M)
                    model.addConstr(kN <= side_bin[s] * M)  # clamp

                    model.addConstr(x[i]        >= io_height - (1 - side_bin[s]) * M)
                    model.addConstr(x[i] + w[i] <= W - io_height + (1 - side_bin[s]) * M)

                elif s == "S":
                    # y == 0
                    model.addConstr(y[i] >= 0 - (1 - side_bin[s]) * M)
                    model.addConstr(y[i] <= 0 + (1 - side_bin[s]) * M)

                    kS = model.addVar(vtype=GRB.INTEGER, name=f"{m._name}_slotS")
                    model.addConstr(x[i] - kS * io_pitch <= (1 - side_bin[s]) * M)
                    model.addConstr(x[i] - kS * io_pitch >= -(1 - side_bin[s]) * M)
                    model.addConstr(kS <= side_bin[s] * M)  # clamp

                    model.addConstr(x[i]        >= io_height - (1 - side_bin[s]) * M)
                    model.addConstr(x[i] + w[i] <= W - io_height + (1 - side_bin[s]) * M)

                elif s == "E":
                    # x+w == W
                    model.addConstr(x[i] + w[i] >= W - (1 - side_bin[s]) * M)
                    model.addConstr(x[i] + w[i] <= W + (1 - side_bin[s]) * M)

                    kE = model.addVar(vtype=GRB.INTEGER, name=f"{m._name}_slotE")
                    model.addConstr(y[i] - kE * io_pitch <= (1 - side_bin[s]) * M)
                    model.addConstr(y[i] - kE * io_pitch >= -(1 - side_bin[s]) * M)
                    model.addConstr(kE <= side_bin[s] * M)  # clamp

                    model.addConstr(y[i]        >= io_height - (1 - side_bin[s]) * M)
                    model.addConstr(y[i] + h[i] <= H - io_height + (1 - side_bin[s]) * M)

                elif s == "W":
                    # x == 0
                    model.addConstr(x[i] >= 0 - (1 - side_bin[s]) * M)
                    model.addConstr(x[i] <= 0 + (1 - side_bin[s]) * M)

                    kW = model.addVar(vtype=GRB.INTEGER, name=f"{m._name}_slotW")
                    model.addConstr(y[i] - kW * io_pitch <= (1 - side_bin[s]) * M)
                    model.addConstr(y[i] - kW * io_pitch >= -(1 - side_bin[s]) * M)
                    model.addConstr(kW <= side_bin[s] * M)  # clamp

                    model.addConstr(y[i]        >= io_height - (1 - side_bin[s]) * M)
                    model.addConstr(y[i] + h[i] <= H - io_height + (1 - side_bin[s]) * M)

        else:  # BGA mode
            kx_ub = max(1, int(math.ceil(max(1.0, Mx - bga_origin_x) / bga_pitch_x)) + 1)
            ky_ub = max(1, int(math.ceil(max(1.0, My - bga_origin_y) / bga_pitch_y)) + 1)

            kx = model.addVar(vtype=GRB.INTEGER, lb=0, ub=kx_ub, name=f"{m._name}_bga_ix")
            ky = model.addVar(vtype=GRB.INTEGER, lb=0, ub=ky_ub, name=f"{m._name}_bga_iy")

            # Snap PAD centers to the legal BGA lattice.
            model.addConstr(x[i] + 0.5 * w[i] == bga_origin_x + kx * bga_pitch_x,
                            name=f"{m._name}_bga_snap_x")
            model.addConstr(y[i] + 0.5 * h[i] == bga_origin_y + ky * bga_pitch_y,
                            name=f"{m._name}_bga_snap_y")

    # ======================
    # Keep non-pad modules out of reserved pad bands only in periphery mode.
    # In BGA mode pads live inside the array, so there is no dedicated edge band.
    # ======================
    io_row_h = chip.get("io_row_h", io_height)  # thickness of top/bottom IO rows
    io_col_w = chip.get("io_col_w", io_height)  # thickness of left/right IO cols

    if pad_mode == "periphery":
        # Only reserve bands where pads are actually allowed
        has_top    = any(m.pad_only and ("N" in (m.pad_sides or ["N","S","E","W"])) for m in mod_list)
        has_bottom = any(m.pad_only and ("S" in (m.pad_sides or ["N","S","E","W"])) for m in mod_list)
        has_left   = any(m.pad_only and ("W" in (m.pad_sides or ["N","S","E","W"])) for m in mod_list)
        has_right  = any(m.pad_only and ("E" in (m.pad_sides or ["N","S","E","W"])) for m in mod_list)

        margin_top    = io_row_h if has_top    else 0.0
        margin_bottom = io_row_h if has_bottom else 0.0
        margin_left   = io_col_w if has_left   else 0.0
        margin_right  = io_col_w if has_right  else 0.0
    else:
        margin_top = margin_bottom = margin_left = margin_right = 0.0

    # Force non-pad modules into the core box
    for i, m in enumerate(mod_list):
        if not m.pad_only:
            model.addConstr(y[i]         >= margin_bottom)
            model.addConstr(y[i] + h[i] <= H - margin_top)
            model.addConstr(x[i]         >= margin_left)
            model.addConstr(x[i] + w[i] <= W - margin_right)


    # ======================
    # Apply user constraints
    # ======================
    for i, m in enumerate(mod_list):
        constraints.apply_regions (model, m._name, x[i], y[i], w[i], h[i])
        constraints.apply_keepouts(model, m._name, x[i], y[i], w[i], h[i], M)

    for i in range(len(mod_list)):
        for j in range(i + 1, len(mod_list)):
            t = model.addVars(4, vtype=GRB.BINARY, name=f"rel_{i}_{j}")
            model.addConstr(t.sum() == 1)
            constraints.apply_halo(model, x, y, w, h, M, t, i, j)

    constraints.apply_symmetry (model, mod_index, x, y, w, h)
    constraints.apply_alignment(model, mod_index, x, y, w, h)
    constraints.apply_proximity(model, mod_index, x, y, w, h)
    constraints.apply_ordering(model, mod_index, x, y, w, h)
    # ======================
    # Variant + orientation -> actual w,h
    # ======================
    sel_vars = {}
    z_map = {}
    for i, m in enumerate(mod_list):
        if len(m.variants) > 1:
            s = [model.addVar(vtype=GRB.BINARY, name=f"s_{m._name}_{j}") for j in range(len(m.variants))]
            model.addConstr(quicksum(s) == 1)
            sel_vars[i] = s

            z = {}
            for j in range(len(m.variants)):
                for r in range(4):
                    z[(j,r)] = model.addVar(vtype=GRB.BINARY, name=f"z_{m._name}_{j}_{r}")
                    model.addConstr(z[(j,r)] <= s[j])
                    model.addConstr(z[(j,r)] <= ori[i][r])
                    model.addConstr(z[(j,r)] >= s[j] + ori[i][r] - 1)

            # Precompute rotated w,h for each (j,r)
            w_expr, h_expr = 0, 0
            for j, vj in enumerate(m.variants):
                w0, h0 = vj["w"], vj["h"]
                w_expr += z[(j,0)]*w0 + z[(j,1)]*h0 + z[(j,2)]*w0 + z[(j,3)]*h0
                h_expr += z[(j,0)]*h0 + z[(j,1)]*w0 + z[(j,2)]*h0 + z[(j,3)]*w0

            model.addConstr(w[i] == w_expr)
            model.addConstr(h[i] == h_expr)
            # stash z for later use in HPWL pin calc
            if "z_map" not in locals(): z_map = {}
            z_map[i] = z

        else:
            v = m.variants[0]
            model.addConstr(w[i] == (ori[i].get(0, 0) + ori[i].get(2, 0)) * v["w"] +
                                     (ori[i].get(1, 0) + ori[i].get(3, 0)) * v["h"])
            model.addConstr(h[i] == (ori[i].get(0, 0) + ori[i].get(2, 0)) * v["h"] +
                                     (ori[i].get(1, 0) + ori[i].get(3, 0)) * v["w"])

        # already bounded above by W,H, but keep for clarity
        model.addConstr(x[i] + w[i] <= W)
        model.addConstr(y[i] + h[i] <= H)

    # ======================
    # HPWL with orientation-aware pins
    # ======================
    if level==0: #For Area with weighted HPWL
        hpwl_terms = []
        for net_name, net_data in nets.items():
            endpoints = net_data["endpoints"]
            weight    = net_data.get("weight", 1.0)  # default = 1.0

            x_min = model.addVar(lb=0, ub=Mx, name=f"{net_name}_xmin")
            x_max = model.addVar(lb=0, ub=Mx, name=f"{net_name}_xmax")
            y_min = model.addVar(lb=0, ub=My, name=f"{net_name}_ymin")
            y_max = model.addVar(lb=0, ub=My, name=f"{net_name}_ymax")

            for ep in endpoints:
                mname = ep["module"]
                idx   = mod_index[mname]
                xi, yi = x[idx], y[idx]

                if idx in z_map:  # multi-variant case
                    px_expr, py_expr = 0, 0
                    for j, vj in enumerate(mod_list[idx].variants):
                        vw, vh = vj["w"], vj["h"]

                        if "pin_index" in ep and vj.get("pins"):
                            k = int(ep["pin_index"])
                            px0, py0 = vj["pins"][k]
                        else:
                            px0, py0 = vw/2, vh/2  # fallback center

                        # R0
                        px_expr += z_map[idx][(j,0)] * px0
                        py_expr += z_map[idx][(j,0)] * py0
                        # R90
                        px_expr += z_map[idx][(j,1)] * py0
                        py_expr += z_map[idx][(j,1)] * (vw - px0)
                        # R180
                        px_expr += z_map[idx][(j,2)] * (vw - px0)
                        py_expr += z_map[idx][(j,2)] * (vh - py0)
                        # R270
                        px_expr += z_map[idx][(j,3)] * (vh - py0)
                        py_expr += z_map[idx][(j,3)] * px0

                    pin_x = x[idx] + px_expr
                    pin_y = y[idx] + py_expr

                else:  # single-variant case
                    vj = mod_list[idx].variants[0]
                    vw, vh = vj["w"], vj["h"]

                    if "pin_index" in ep and vj.get("pins"):
                        k = int(ep["pin_index"])
                        px0, py0 = vj["pins"][k]
                    else:
                        px0, py0 = vw/2, vh/2

                    b0 = ori[idx].get(0, 0)
                    b1 = ori[idx].get(1, 0)
                    b2 = ori[idx].get(2, 0)
                    b3 = ori[idx].get(3, 0)

                    px_expr = b0*px0 + b1*py0 + b2*(vw - px0) + b3*(vh - py0)
                    py_expr = b0*py0 + b1*(vw - px0) + b2*(vh - py0) + b3*px0

                    pin_x = x[idx] + px_expr
                    pin_y = y[idx] + py_expr



                model.addConstr(x_min <= pin_x)
                model.addConstr(x_max >= pin_x)
                model.addConstr(y_min <= pin_y)
                model.addConstr(y_max >= pin_y)

            # multiply by net weight
            hpwl_terms.append(weight * ((x_max - x_min) + (y_max - y_min)))

        total_hpwl = quicksum(hpwl_terms)
        model.setObjective((1-weight_hpwl)*(W * H) + weight_hpwl*total_hpwl, GRB.MINIMIZE)

    elif level == 1: #For Area with weighted HPWL and additional branch specific weight term
        branch_factor_weight = 1
        hpwl_terms = []
        branch_terms = []

        # -----------------------------
        # 1. NORMAL HPWL (LEVEL 0)
        # -----------------------------
        for net_name, net_data in nets.items():
            endpoints = net_data["endpoints"]
            w_net = net_data.get("weight", 1.0)

            # bounding box vars
            x_min = model.addVar(lb=0, ub=Mx, name=f"{net_name}_xmin")
            x_max = model.addVar(lb=0, ub=Mx, name=f"{net_name}_xmax")
            y_min = model.addVar(lb=0, ub=My, name=f"{net_name}_ymin")
            y_max = model.addVar(lb=0, ub=My, name=f"{net_name}_ymax")

            # compute bbox from endpoints (same as level 0)
            for ep in endpoints:

                # --- EXACTLY SAME pin computation logic ---
                mname = ep["module"]
                idx   = mod_index[mname]
                xi, yi = x[idx], y[idx]

                # Variant and pin orientation handling unchanged
                pin_x, pin_y = compute_pin_position(idx, ep, x, y, z_map, ori, mod_list)

                model.addConstr(x_min <= pin_x)
                model.addConstr(x_max >= pin_x)
                model.addConstr(y_min <= pin_y)
                model.addConstr(y_max >= pin_y)

            hpwl_terms.append(w_net * ((x_max - x_min) + (y_max - y_min)))

        # -------------------------------------
        # 2. ADD WEIGHTED BRANCH DISTANCES
        # -------------------------------------
        for net_name, net_data in nets.items():

            if "branches" not in net_data:
                continue

            for (epA_name, epB_name, w_branch) in net_data["branches"]:
                
                if w_branch == 0:
                    continue

                # ---- Resolve epA and epB endpoints ----
                epA = resolve_endpoint(epA_name, nets[net_name]["endpoints"])
                epB = resolve_endpoint(epB_name, nets[net_name]["endpoints"])

                # ---- Compute pin coords using SAME logic ----
                pinAx, pinAy = compute_pin_position(
                    mod_index[epA["module"]],
                    epA, x, y, z_map, ori, mod_list
                )
                pinBx, pinBy = compute_pin_position(
                    mod_index[epB["module"]],
                    epB, x, y, z_map, ori, mod_list
                )

                # ---- Linearize Manhattan distance ----
                dx = model.addVar(lb=0, name=f"{net_name}_dx_{epA_name}_{epB_name}")
                dy = model.addVar(lb=0, name=f"{net_name}_dy_{epA_name}_{epB_name}")

                model.addConstr(dx >= pinAx - pinBx)
                model.addConstr(dx >= pinBx - pinAx)
                model.addConstr(dy >= pinAy - pinBy)
                model.addConstr(dy >= pinBy - pinAy)

                # add weighted branch term
                branch_terms.append(w_branch * (dx + dy))

        total_obj = quicksum(hpwl_terms) + branch_factor_weight * quicksum(branch_terms)
        model.setObjective((1-weight_hpwl)*(W * H) + weight_hpwl*total_obj, GRB.MINIMIZE)





    # ----------------------------
    # Step 1: Run automated tuning
    # ----------------------------
    # ----------------------------
    # Automated parameter tuning
    # ----------------------------
    #model.setParam("TuneTrials",     20)     # explore ~20 combinations
    model.setParam("TimeLimit",      timelimit)    # each trial: 3 minutes
    #model.setParam("TuneTimeLimit",  600)   # total: 10 minutes
    #model.setParam("TuneOutput",     2)      # verbose tuner progress
    #model.setParam("TuneCriterion",  1)      # use wall-clock runtime as objective
    #model.setParam("TuneTargetMIPGap", 1e-3) # compare configs at same target gap


    #print("===== Starting Gurobi automated tuning =====")
    #model.tune()
    #print("===== Tuning complete =====")

    # Save best parameter configuration
    #try:
    #    nresults = model.tuneResultCount
    #except AttributeError:
        # For older Gurobi versions (<9.5)
    #    nresults = model.GetTuneResultCount()

    #if nresults > 0:
    #    try:
    #        model.GetTuneResult(0)
    #    except AttributeError:
    #        model.getTuneResult(0)
    #    model.write("best_params.prm")
    #    print("Saved best parameter configuration to best_params.prm")

    #model.read("best_params.prm")
    #    model.setParam("TimeLimit",      30)    # each trial: 3 minutes
    # --- Ensure model._modules contains Module objects ---
    if isinstance(list(modules.values())[0], Module):
        model._modules = list(modules.values())       # good case: dict of Module objects
    elif isinstance(modules[0], Module):
        model._modules = modules                      # already a list of Module objects
    elif isinstance(modules[0], str):
        # modules is list of names -> fetch the objects from global module_dict
        model._modules = [module_dict[name] for name in modules]
    else:
        raise TypeError(f"Unexpected type for modules: {type(modules[0])}")

    # Initialize snapshot list and run ILP
    model._snapshots = []
    model.optimize(ilp_callback)


    #model.optimize()



    # ======================
    # Extract solution
    # ======================
    placement, dims, pins_used = {}, {}, {}
    if model.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT):
        for i, m in enumerate(mod_list):
            xi, yi = x[i].X, y[i].X
            wi, hi = w[i].X, h[i].X
            ori_vals = {r: int(var.X) for r, var in ori[i].items()}
            ori_val  = max(ori_vals, key=ori_vals.get)  # chosen orientation
            variant_idx = 0
            if i in sel_vars:
                s_vals = [var.X for var in sel_vars[i]]
                variant_idx = max(range(len(s_vals)), key=lambda j: s_vals[j])

            gds_file = m.variants[variant_idx].get("gds_file", None)
            dummy_gds_file = m.variants[variant_idx].get("dummy_gds_file", None)
            
            placement[m._name] = (xi, yi, ori_val, gds_file, dummy_gds_file)
            dims[m._name]      = (wi, hi)

            pins = []
            vw, vh = m.variants[variant_idx]["w"], m.variants[variant_idx]["h"]
            for (px0, py0) in m.variants[variant_idx].get("pins", []):
                px, py = rotate_pin(px0, py0, vw, vh, ori_val)
                pins.append((px, py))
            pins_used[m._name] = pins


        chip["W"], chip["H"] = W.X, H.X
    # ======================
    # Post-solve pad-grid assertion
    # ======================
    tol = 1e-6  # numerical tolerance
    for i, m in enumerate(mod_list):
        if m.pad_only:
            xi, yi = x[i].X, y[i].X
            wi, hi = w[i].X, h[i].X
            ori_vals = {r: int(var.X) for r, var in ori[i].items()}
            ori_val  = max(ori_vals, key=ori_vals.get)

            if pad_mode == "periphery":
                side = None
                for s, r in side_to_ori.items():
                    if abs(ori_vals.get(r, 0) - 1) < 0.5:
                        side = s
                        break

                #if side in ("N", "S"):
                #    snapped = xi % io_pitch
                #    ok = (snapped < tol) or (io_pitch - snapped < tol)
                #    print(f"[CHECK] Pad {m._name} on {side}: x={xi:.3f}, x%pitch={snapped:.3f}, OK={ok}")
                #    assert ok, f"Pad {m._name} not aligned to io_pitch on {side}"
                #elif side in ("E", "W"):
                #    snapped = yi % io_pitch
                #    ok = (snapped < tol) or (io_pitch - snapped < tol)
                #    print(f"[CHECK] Pad {m._name} on {side}: y={yi:.3f}, y%pitch={snapped:.3f}, OK={ok}")
                #    assert ok, f"Pad {m._name} not aligned to io_pitch on {side}"
            else:
                cx = xi + 0.5 * wi
                cy = yi + 0.5 * hi
                sx = (cx - bga_origin_x) / bga_pitch_x
                sy = (cy - bga_origin_y) / bga_pitch_y
                okx = abs(sx - round(sx)) < tol
                oky = abs(sy - round(sy)) < tol
                print(f"[CHECK] Pad {m._name} in BGA mode: cx={cx:.3f}, cy={cy:.3f}, okx={okx}, oky={oky}")
                assert okx and oky, f"Pad {m._name} is not snapped to the BGA lattice"
    print("\n===== Variable and Constraint Summary =====")

    # Direct attributes (safe on all versions)
    print("Total vars:", model.NumVars)
    print("  Binary vars     :", model.NumBinVars)
    print("  General int vars:", model.NumIntVars)

    # Count vars by their VType
    vars = model.getVars()

    n_bin  = sum(v.VType == 'B' for v in vars)
    n_int  = sum(v.VType == 'I' for v in vars)
    n_cont = sum(v.VType == 'C' for v in vars)
    n_scon = sum(v.VType == 'S' for v in vars)   # semi-continuous
    n_sint = sum(v.VType == 'N' for v in vars)   # semi-integer

    print("  Continuous vars :", n_cont)
    print("  Semi-cont vars  :", n_scon)
    print("  Semi-int vars   :", n_sint)

    # Consistency check
    print("  (Check sum)     :", n_bin + n_int + n_cont + n_scon + n_sint)

    # Constraints
    print("Total linear constraints :", model.NumConstrs)
    print("Total quadratic constrs  :", model.NumQConstrs)
    print("==========================================\n")



    return placement, dims, pins_used

# =========================
# Plotting
# =========================
def plot_solution(
    chip, modules, keepouts, placement, halo, dims, nets, pins_used,
    out_file="floorplan.png", title="ILP Floorplan",
    *,
    mode="png",                  # "png" or "interactive"
    nets_mode="lines",           # "none", "bbox", "lines"
    draw_grid=False,
    draw_pins=False,
    label_pins=False,
    draw_pin_centroid=False,
    draw_keepouts_fill=False,
    draw_halo=True,
    draw_module_sizes=False,
    draw_regions=False,
    draw_symmetry_axis=False,
    constraints=None,
    show=True
):
    W, H, pitch = chip.get("W", 0), chip.get("H", 0), chip.get("pitch", 0)

    if mode == "png":
        # =======================
        # Static Matplotlib Plot
        # =======================
        fig, ax = plt.subplots(figsize=(9, 7))
        ax.add_patch(Rectangle((0, 0), W, H, fill=False, linewidth=2))

        # Grid
        if draw_grid and pitch > 0:
            for gx in range(0, int(W)+1, pitch):
                ax.plot([gx, gx], [0, H], linewidth=0.5, alpha=0.3)
            for gy in range(0, int(H)+1, pitch):
                ax.plot([0, W], [gy, gy], linewidth=0.5, alpha=0.3)

        # Keepouts
        for (x0, y0, x1, y1) in keepouts:
            if draw_keepouts_fill:
                ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=True, alpha=0.08))
            ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=False, linestyle=":", linewidth=1.0))
            ax.text((x0+x1)/2, (y0+y1)/2, "KO", ha="center", va="center", fontsize=8)

        # Symmetry axis
        if draw_symmetry_axis and constraints and getattr(constraints, "symmetry", None):
            xsym = constraints.symmetry.get("vertical_axis_x")
            if xsym is not None:
                ax.plot([xsym, xsym], [0, H], linestyle="--", linewidth=1.2)
                ax.text(xsym, H, "sym-x", ha="center", va="bottom", fontsize=8)

        # Regions
        if draw_regions:
            for mname, mod in modules.items():
                if getattr(mod, "region", None):
                    x0, y0, x1, y1 = mod.region
                    ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=False, linestyle="--", linewidth=0.8))
                    ax.text(x0, y1, f"{mname}:region", fontsize=7, va="bottom")

        # Modules
        for m, (x0, y0, *_) in placement.items():
            w, h = dims[m]
            is_pad = getattr(modules[m], "pad_only", False)

            ax.add_patch(Rectangle((x0, y0), w, h, fill=False,
                                   linewidth=2.2 if is_pad else 1.8,
                                   linestyle="--" if is_pad else "-"))
            if draw_halo and halo > 0:
                ax.add_patch(Rectangle((x0-halo, y0-halo), w+2*halo, h+2*halo,
                                       fill=False, linestyle=":", linewidth=0.8, alpha=0.9))
            label = m
            if draw_module_sizes:
                label += f"\n{int(w)}x{int(h)}"
            ax.text(x0+w/2, y0+h/2, label, ha="center", va="center", fontsize=9)

            if draw_pins and m in pins_used:
                for idx, (px, py) in enumerate(pins_used[m]):
                    ax.plot(x0+px, y0+py, marker="o", markersize=3)
                    if label_pins:
                        ax.text(x0+px+0.8, y0+py+0.8, f"{idx}", fontsize=7)

        # Nets
        if nets_mode in ("bbox", "lines") and nets:
            for net_name, endpoints in nets.items():
                pts = []
                for ep in endpoints:
                    m = ep["module"]; x0, y0, *_ = placement[m]
                    if "pin" in ep:
                        px, py = ep["pin"]
                    elif "pin_index" in ep and len(pins_used.get(m, [])) > 0:
                        k = int(ep["pin_index"])
                        px, py = pins_used[m][k] if 0 <= k < len(pins_used[m]) else (0,0)
                    elif pins_used.get(m, []):
                        px = sum(p[0] for p in pins_used[m])/len(pins_used[m])
                        py = sum(p[1] for p in pins_used[m])/len(pins_used[m])
                    else:
                        px = py = 0
                    pts.append((x0+px, y0+py))

                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                if nets_mode == "bbox":
                    ax.add_patch(Rectangle((min(xs), min(ys)), max(xs)-min(xs), max(ys)-min(ys),
                                           fill=False, linestyle="--", linewidth=1.0))
                    ax.text(min(xs), max(ys), f"{net_name}", va="bottom", fontsize=8)
                else:
                    cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
                    for (px, py) in pts:
                        ax.plot([px, cx], [py, cy], linestyle="--", linewidth=0.8)
                    if draw_pin_centroid:
                        ax.plot(cx, cy, marker="x", markersize=5)
                    ax.text(cx, cy, net_name, fontsize=8, ha="left", va="bottom")

        ax.set_xlim(-1, W+1); ax.set_ylim(-1, H+1)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(title)
        plt.tight_layout()
        plt.savefig(out_file, dpi=220)
        if show: plt.show()
        plt.close(fig)
        return out_file

    elif mode == "interactive":
        # =======================
        # Interactive Plotly Plot
        # =======================
        fig = go.Figure()
        fig.add_shape(type="rect", x0=0, y0=0, x1=W, y1=H,
                      line=dict(width=3, color="black"), fillcolor="rgba(0,0,0,0)")

        # Keepouts
        for (x0, y0, x1, y1) in keepouts:
            fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                          line=dict(dash="dot", color="red"),
                          fillcolor="rgba(255,0,0,0.1)" if draw_keepouts_fill else "rgba(0,0,0,0)")
            fig.add_trace(go.Scatter(x=[(x0+x1)/2], y=[(y0+y1)/2], text=["KO"], mode="text"))

        # Modules
        for m, (x0, y0, *_) in placement.items():
            w, h = dims[m]
            is_pad = getattr(modules[m], "pad_only", False)

            fig.add_shape(type="rect", x0=x0, y0=y0, x1=x0+w, y1=y0+h,
                          line=dict(width=2, color="blue" if is_pad else "black",
                                    dash="dot" if is_pad else "solid"),
                          fillcolor="rgba(0,0,255,0.05)" if is_pad else "rgba(0,0,0,0)")
            if draw_halo and halo > 0:
                fig.add_shape(type="rect", x0=x0-halo, y0=y0-halo, x1=x0+w+halo, y1=y0+h+halo,
                              line=dict(width=1, dash="dot", color="gray"), fillcolor="rgba(0,0,0,0)")

            label = m
            if draw_module_sizes: label += f"<br>{int(w)}x{int(h)}"
            fig.add_trace(go.Scatter(x=[x0+w/2], y=[y0+h/2], text=[label], mode="text"))

            if draw_pins and m in pins_used:
                pxs, pys = [], []
                for idx, (px, py) in enumerate(pins_used[m]):
                    pxs.append(x0+px); pys.append(y0+py)
                    if label_pins:
                        fig.add_trace(go.Scatter(x=[x0+px], y=[y0+py],
                                                 text=[str(idx)], mode="text", textposition="top right"))
                fig.add_trace(go.Scatter(x=pxs, y=pys, mode="markers",
                                         marker=dict(size=6, color="green"),
                                         name=f"{m}_pins"))

        # Nets
        if nets_mode in ("bbox", "lines") and nets:
            for net_name, net_data in nets.items():
                endpoints = net_data["endpoints"]
                pts = []
                for ep in endpoints:
                    m = ep["module"]; x0, y0, *_ = placement[m]
                    if "pin_index" in ep and len(pins_used.get(m, [])) > 0:
                        k = int(ep["pin_index"])
                        px, py = pins_used[m][k] if 0 <= k < len(pins_used[m]) else (dims[m][0]/2, dims[m][1]/2)
                    else:
                        px, py = dims[m][0]/2, dims[m][1]/2
                    pts.append((x0+px, y0+py))
                xs, ys = zip(*pts)
                if nets_mode == "bbox":
                    fig.add_shape(type="rect", x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys),
                                  line=dict(dash="dot", color="orange"))
                    fig.add_trace(go.Scatter(x=[min(xs)], y=[max(ys)],
                                             text=[f"{net_name}"], mode="text"))
                else:
                    cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
                    for (px, py) in pts:
                        fig.add_trace(go.Scatter(x=[px, cx], y=[py, cy],
                                                 mode="lines", line=dict(dash="dot", width=1, color="orange"),
                                                 showlegend=False))
                    fig.add_trace(go.Scatter(x=[cx], y=[cy],
                                             text=[net_name], mode="text", textposition="top left"))

        fig.update_layout(title=title,
                          xaxis=dict(range=[-1, W+1], scaleanchor="y", scaleratio=1,
                                     showgrid=False, zeroline=False),
                          yaxis=dict(range=[-1, H+1], showgrid=False, zeroline=False),
                          width=1920, height=1080)
        fig.write_html(out_file)
        if show: fig.show()
        return out_file

    else:
        raise ValueError(f"Unsupported mode: {mode}")

def export_verilog_json(chip, modules, placement, dims, pins_used, nets, out_json):
    """
    Export placement into a placement.verilog.json file.
    Pin coordinates are exported in absolute chip coordinates
    after applying placement (x,y) and CLOCKWISE orientation.
    """
    data = {
        "chip": {"W": chip.get("W", 0), "H": chip.get("H", 0)},
        "modules": {},
        "nets": nets
    }

    for mname, entry in placement.items():
        if len(entry) == 5:
            x, y, ori, gds_file, dummy_gds_file = entry
        else:
            x, y, ori = entry
            gds_file = None
            dummy_gds_file = None

        w, h = dims[mname]

        # Base variant (unrotated, local pin coords)
        variant_pins = modules[mname].variants[0].get("pins", [])
        vw, vh = modules[mname].variants[0]["w"], modules[mname].variants[0]["h"]

        pins_abs = []
        for (px, py) in pins_used[mname]:
            pins_abs.append({"x": int(x + px), "y": int(y + py)})



        data["modules"][mname] = {
            "x": int(x),
            "y": int(y),
            "w": int(w),
            "h": int(h),
            "orientation": int(ori),
            "gds_file": gds_file,
            "dummy_gds_file": dummy_gds_file,
            "pins": pins_abs
        }

    with open(out_json, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"export_verilog_json(): wrote {out_json}")
    return out_json



# =========================
# Main
# =========================
if __name__ == "__main__":

    print(f"RUNNING PLACER")

    parser = argparse.ArgumentParser(
        description="Generate floorplan of the design from the parsed netlist and generated primitive blocks."
    )
    parser.add_argument("--config", default="config.json", help="Input config.json with all user inputs")
    args = parser.parse_args()
    cfg = load_config(args.config)

    project_dir=cfg["project_name"]
    top_name = cfg["topcell"]
    stage_2_dir = os.path.join(project_dir, "stage_2")
    stage_3_dir = os.path.join(project_dir, "stage_3", "placement")
    os.makedirs(stage_3_dir, exist_ok=True)
    stage_2_design = os.path.join(stage_2_dir, f"{top_name}_design.json")
    chip, modules, nets = load_design(stage_2_design)
    constraints = load_constraints(cfg["placement"]["placement_constraints"])



    timelimit = cfg["placement"]["timelimit"]
    ar = cfg["placement"]["aspect_ratio"]
    aspect_ratio = None if ar == 0 else ar


    placement, dims, pins_used = gurobi_floorplan(chip, modules, nets, constraints, timelimit=timelimit, aspect_ratio=aspect_ratio, level = cfg["placement"]["level"], weight_hpwl =  cfg["placement"]["weight_hpwl"])

    if placement:
        print("Placement result:", placement)
        
        if cfg["placement"]["plot_html"] == True:
            plot_solution(
                chip, modules, keepouts=[], placement=placement,
                halo=0, dims=dims, nets=nets, pins_used=pins_used,
                out_file = "floorplan.html", title="ILP Floorplan",
                nets_mode="none", draw_pins=True, label_pins=True, show=False, mode="interactive"
            )
        placement_output = os.path.join(stage_3_dir, f"{top_name}_placement.json")
        export_verilog_json(chip=chip, modules=modules, placement=placement,dims=dims, pins_used=pins_used, nets= nets, out_json=placement_output)
        output_gds = os.path.join(stage_3_dir, f"{top_name}_placement.gds")
        final_primitives = os.path.join(stage_3_dir, "primitives")
        os.makedirs(final_primitives, exist_ok = True)
        gen_placement_gds.build_layout_from_json(
            json_file=placement_output,
            out_gds=output_gds,
            scale=cfg["scale"],
            copy_gds_to=final_primitives,
            snap_all_after_flat=True
        )





#!/usr/bin/env python3

import argparse
import json
import math
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Modify a SPICE netlist by appending annotations from a design JSON using an external mapping JSON."
    )
    parser.add_argument("--netlist", required=True, help="Input .sp netlist file")
    parser.add_argument("--design-json", required=True, help="Input design JSON file")
    parser.add_argument("--mapping-json", required=True, help="Instance-to-JSON mapping file")
    parser.add_argument("--output", required=True, help="Output modified .sp netlist file")
    parser.add_argument(
        "--design-key",
        default=None,
        help="Top-level key in the design JSON. If omitted, the first top-level key is used.",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def get_design_parameters(data, design_key=None):
    if not isinstance(data, dict) or not data:
        raise ValueError("Design JSON is empty or not a dictionary.")

    if design_key is None:
        design_key = next(iter(data.keys()))

    if design_key not in data:
        raise KeyError(f"Design key '{design_key}' not found in design JSON.")

    block = data[design_key]

    if "Design_Parameters" not in block:
        raise KeyError(f"'Design_Parameters' not found under top-level key '{design_key}'.")

    return block["Design_Parameters"], design_key


def get_leading_whitespace(line):
    m = re.match(r"^(\s*)", line)
    return m.group(1) if m else ""


def split_comment(line):
    if ";" in line:
        main, comment = line.split(";", 1)
        return main.rstrip(), ";" + comment
    return line.rstrip("\n"), ""


def strip_existing_trailing_annotation(main_part):
    return re.sub(r"\s+\([^()]*\)\s*$", "", main_part).rstrip()


def should_skip_line(stripped):
    if not stripped:
        return True
    if stripped.startswith("*"):
        return True
    if stripped.startswith(".subckt"):
        return True
    if stripped.startswith(".ends"):
        return True
    if stripped.startswith(".end"):
        return True
    return False


def try_parse_number(x):
    if isinstance(x, (int, float)):
        return x

    if isinstance(x, str):
        s = x.strip()
        if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s):
            return float(s)

    return x


def clean_number(x):
    x = try_parse_number(x)

    if x is None:
        return "-1"

    if isinstance(x, str):
        return x

    if math.isclose(float(x), round(float(x)), rel_tol=0.0, abs_tol=1e-12):
        return str(int(round(float(x))))

    return f"{float(x):.2f}"

def format_annotation(values):
    return "(" + " ".join(clean_number(v) for v in values) + ")"


def get_value_with_default(design_params, key, default=None):
    if key in design_params and design_params[key] is not None:
        return design_params[key]
    return default


def build_annotation_from_mapping(instance_name, mapping_cfg, design_params):
    """
    Supported mapping modes:

    1. json_list
       Example:
       "drain_ind": {
           "mode": "json_list",
           "json_keys": ["DRAIN_IND_L", "DRAIN_IND_Q", "DRAIN_IND_PEAK_Q", "DRAIN_IND_SRF"],
           "defaults": [-1, -1, -1, -1]
       }

    2. regex_extract
       Example:
       "cas_mos": {
           "mode": "regex_extract",
           "source_key": "CASMOS_Size",
           "pattern": "\\s*([0-9]*\\.?[0-9]+)\\s*\\*\\s*([0-9]*\\.?[0-9]+)\\s*um\\s*/\\s*([0-9]*\\.?[0-9]+)\\s*nm\\s*"
       }
    """

    if instance_name not in mapping_cfg:
        return None

    rule = mapping_cfg[instance_name]
    mode = rule.get("mode", "json_list")

    if mode == "json_list":
        json_keys = rule.get("json_keys", [])
        defaults = rule.get("defaults", [])

        values = []
        for i, key in enumerate(json_keys):
            default_val = defaults[i] if i < len(defaults) else None
            val = get_value_with_default(design_params, key, default_val)

            # If missing and no default is provided, skip annotation
            if val is None:
                return None

            values.append(val)

        return format_annotation(values)

    if mode == "regex_extract":
        source_key = rule.get("source_key")
        pattern = rule.get("pattern")
        defaults = rule.get("defaults", [])

        if not source_key or not pattern:
            return None

        raw_val = design_params.get(source_key)
        if raw_val is None:
            return None

        m = re.match(pattern, str(raw_val), flags=re.IGNORECASE)
        if not m:
            return None

        groups = list(m.groups())

        # Fill defaults if user wants more output fields than regex groups
        if defaults:
            while len(groups) < len(defaults):
                groups.append(defaults[len(groups)])

        return format_annotation(groups)

    return None


def modify_netlist_lines(lines, design_params, mapping_cfg):
    modified = []

    for line in lines:
        original_line = line.rstrip("\n")
        leading_ws = get_leading_whitespace(original_line)

        if not original_line.strip():
            modified.append(original_line)
            continue

        stripped = original_line.strip()

        if should_skip_line(stripped):
            modified.append(original_line)
            continue

        main_part, comment_part = split_comment(original_line)
        tokens = main_part.split()

        if not tokens:
            modified.append(original_line)
            continue

        instance_name = tokens[0]

        annotation = build_annotation_from_mapping(
            instance_name=instance_name,
            mapping_cfg=mapping_cfg,
            design_params=design_params,
        )

        if annotation is None:
            modified.append(original_line)
            continue

        cleaned_main = strip_existing_trailing_annotation(main_part.strip())
        new_line = f"{leading_ws}{cleaned_main} {annotation}"

        if comment_part:
            new_line += " " + comment_part

        modified.append(new_line)

    return modified


def main():
    args = parse_args()

    design_data = load_json(args.design_json)
    mapping_data = load_json(args.mapping_json)

    design_params, used_design_key = get_design_parameters(
        design_data,
        args.design_key
    )

    with open(args.netlist, "r") as f:
        lines = f.readlines()

    modified_lines = modify_netlist_lines(
        lines=lines,
        design_params=design_params,
        mapping_cfg=mapping_data
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("\n".join(modified_lines) + "\n")

    print(f"Used design key: {used_design_key}")
    print(f"Modified netlist written to: {output_path}")


if __name__ == "__main__":
    main()

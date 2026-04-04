#!/usr/bin/env python3
"""
Combine multiple LEF files into a single LEF file.
Each LEF is assumed to contain valid MACRO ... END blocks.
"""

import os
import argparse

def combine_lefs(input_dir, output_file):
    with open(output_file, "w") as outfile:
        for fname in sorted(os.listdir(input_dir)):
            if fname.lower().endswith(".lef"):
                fpath = os.path.join(input_dir, fname)
                with open(fpath, "r") as infile:
                    contents = infile.read().strip()
                    if not contents:
                        continue
                    # Write contents followed by a blank line for safety
                    outfile.write(contents + "\n")
                print(f"Appended {fname} to {output_file}")
    print(f"Combined LEF written to {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Combine individual LEF files into one.")
    parser.add_argument("-i", "--input_dir", type=str, required=True,
                        help="Directory containing individual LEF files")
    parser.add_argument("-o", "--output", type=str, required=True,
                        help="Path to the combined LEF file")
    args = parser.parse_args()

    combine_lefs(args.input_dir, args.output)

if __name__ == "__main__":
    main()


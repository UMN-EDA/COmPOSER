import numpy as np

import argparse
import os
import sys

def suggest_resistor_dims(R_target, Rsheet=756.206,
                          W_min=0.8, W_max=10,
                          L_min=0.8, L_max=100,
                          n_W=100, n_L=500, k=10):
    """
    Sweep feasible (W,L) pairs and return up to k (W, L) tuples
    closest to the target resistance.

    Parameters
    ----------
    R_target : float
        Desired resistance
    Rsheet : float
        Sheet resistance (Ohm/sq)
    W_min, W_max, L_min, L_max : float
        Dimension bounds
    n_W, n_L : int
        Grid resolution along W and L
    k : int
        Max number of solutions to return

    Returns
    -------
    list[tuple[float, float]]
        Up to k (W, L) pairs rounded to 2 decimals
    """
    Ws = np.linspace(W_min, W_max, n_W)
    Ls = np.linspace(L_min, L_max, n_L)

    results = []
    for W in Ws:
        for L in Ls:
            R_pred = Rsheet * (L / W)
            err = abs(R_pred - R_target)
            results.append((round(W, 2), round(L, 2), R_pred, err))

    # sort by error and keep only W,L
    results.sort(key=lambda x: x[3])
    return [(l, w, round(r_pred,2)) for w, l, r_pred, _ in results[:k]]



def parse_args():
    parser = argparse.ArgumentParser(
        description="Suggest resistor dimensions for a target resistance"
    )

    parser.add_argument(
        "--R_target",
        type=float,
        default=1000.0,
        help="Target resistance in ohms (default: 1000.0)"
    )

    parser.add_argument(
        "--Rsheet",
        type=float,
        default=756.206,
        help="Sheet resistance in ohms/square (default: 756.206)"
    )

    parser.add_argument(
        "--W_min",
        type=float,
        default=0.8,
        help="Minimum resistor width in um (default: 0.8)"
    )

    parser.add_argument(
        "--W_max",
        type=float,
        default=10.0,
        help="Maximum resistor width in um (default: 10.0)"
    )

    parser.add_argument(
        "--L_min",
        type=float,
        default=0.8,
        help="Minimum resistor length in um (default: 0.8)"
    )

    parser.add_argument(
        "--L_max",
        type=float,
        default=100.0,
        help="Maximum resistor length in um (default: 100.0)"
    )

    parser.add_argument(
        "--n_W",
        type=int,
        default=100,
        help="Number of width grid points (default: 100)"
    )

    parser.add_argument(
        "--n_L",
        type=int,
        default=500,
        help="Number of length grid points (default: 500)"
    )

    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="Maximum number of candidate solutions to return (default: 10)"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 80)
    print("Resistor dimension suggester")
    print("=" * 80)
    print(f"Target resistance (ohm) : {args.R_target}")
    print(f"Sheet resistance        : {args.Rsheet}")
    print(f"W min / W max (um)      : {args.W_min} / {args.W_max}")
    print(f"L min / L max (um)      : {args.L_min} / {args.L_max}")
    print(f"n_W / n_L               : {args.n_W} / {args.n_L}")
    print(f"Top k candidates        : {args.k}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name}")
    print(f"  Custom  : python {script_name} --R_target 1000 --W_min 2 --W_max 10 --n_W 300 --n_L 300 --k 5")
    print("=" * 80)

    candidates = suggest_resistor_dims(
        R_target=args.R_target,
        Rsheet=args.Rsheet,
        W_min=args.W_min,
        W_max=args.W_max,
        L_min=args.L_min,
        L_max=args.L_max,
        n_W=args.n_W,
        n_L=args.n_L,
        k=args.k
    )

    print("\nCandidate resistor dimensions:\n")
    for i, (L, W, R_pred) in enumerate(candidates, 1):
        print(f"{i:2d}. L = {L:.2f} um, W = {W:.2f} um, Predicted R = {R_pred:.2f} ohm")

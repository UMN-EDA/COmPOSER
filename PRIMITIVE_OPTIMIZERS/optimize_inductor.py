import numpy as np, pandas as pd, os, time
from joblib import load
from sklearn.neighbors import NearestNeighbors
from . import knn_with_emx_estimator_geom_predictor as my_knn
from . import emx_estimator as my_emx

base = os.environ["PROJECT_HOME"]           # get the directory

def knn_candidates(target_specs, knn_model, knn_train_data, n_neighbors=1000):
    """
    Use kNN to get candidate geometries near the target specs.
    Any None/NaN in target_specs is replaced with 0 for the query vector.
    """
    filled = [0 if (v is None or np.isnan(v)) else v for v in target_specs]
    distances, indices = knn_model.kneighbors([filled], n_neighbors=n_neighbors)
    return knn_train_data[indices[0]]

def optimize_specs(
    target_specs,
    emx_estimator_model,
    knn_model,
    knn_train_data,
    n_neighbors=5000
):
    """
    Optimize geometry using only kNN candidate points
    instead of scanning the entire CSV.
    """
    spec_cols = ["Inductance", "Peak Q", "Peak Q Freq", "SRF"]
    geom_cols = ["Radius", "Width", "Spacing", "Turns"]

    target_specs = np.array(target_specs, dtype=float)
    if target_specs.shape[0] != 4:
        raise ValueError("target_specs must have exactly 4 values.")

    print(f"\n? Starting kNN-based optimization with target specs {target_specs}")

    start_time = time.time()

    # --- Get candidate geometries from kNN ---
    candidate_geoms = knn_candidates(target_specs, knn_model, knn_train_data, n_neighbors)
    if candidate_geoms.size == 0:
        raise RuntimeError("No candidates returned by kNN.")

    # --- Predict specs for those geometries ---
    pred_specs = emx_estimator_model.predict(candidate_geoms)

    fixed_idxs = [i for i, v in enumerate(target_specs) if not np.isnan(v)]
    free_idxs  = [i for i in range(4) if i not in fixed_idxs]

    # === Case 1: all 4 specs fixed ? pure nearest neighbor ===
    if len(fixed_idxs) == 4:
        # Compute L2 distance to the target spec
        dists = np.linalg.norm(pred_specs - target_specs, axis=1)
        best_idx = np.argmin(dists)
        mode = "exact_match"
    else:
        # === Case 2: match fixed specs, maximize free specs ===
        diff_penalty = np.sum(
            (pred_specs[:, fixed_idxs] - target_specs[fixed_idxs])**2, axis=1
        )
        gain = np.sum(pred_specs[:, free_idxs], axis=1)
        score = gain - diff_penalty
        best_idx = np.argmax(score)
        mode = "partial_match"

    elapsed = time.time() - start_time

    print(f"\n? kNN-based optimization done in {elapsed:.2f} s")
    for i, c in enumerate(spec_cols):
        print(f"  {c}: {pred_specs[best_idx, i]:.2f}")
    print("Geometry:", dict(zip(geom_cols, candidate_geoms[best_idx])))

    return {
        "mode": mode,
        "target_specs": target_specs,
        "pred_spec": pred_specs[best_idx],
        "geometry": candidate_geoms[best_idx]
    }

def optimize_specs_multi_variant(
    target_specs,
    emx_estimator_model,
    knn_model,
    knn_train_data,
    n_neighbors=5000,
    four_variants=True,
    max_rel_err=0.1
):
    spec_cols = ["Inductance", "Peak Q", "Peak Q Freq", "SRF"]
    geom_cols = ["Radius", "Width", "Spacing", "Turns"]
    target_specs = np.array(target_specs, dtype=float)

    if target_specs.shape[0] != 4:
        raise ValueError("target_specs must have exactly 4 values.")

    def single_variant(offsets):
        candidate_geoms = knn_candidates(target_specs, knn_model, knn_train_data, n_neighbors)

        tol = 1e-6
        mask = np.zeros(len(candidate_geoms), dtype=bool)
        for off in offsets:
            mask |= np.abs((candidate_geoms[:, 3] - off) % 1.0) < tol
        candidate_geoms = candidate_geoms[mask]
        if candidate_geoms.size == 0:
            return None

        pred_specs = emx_estimator_model.predict(candidate_geoms)
        fixed_idxs = [i for i, v in enumerate(target_specs) if not np.isnan(v)]
        free_idxs  = [i for i in range(4) if i not in fixed_idxs]

        if len(fixed_idxs) == 4:
            dists = np.linalg.norm(pred_specs - target_specs, axis=1)
            best_idx = np.argmin(dists)
            return {
                "mode": "exact_match",
                "target_specs": target_specs,
                "pred_spec": pred_specs[best_idx],
                "geometry": candidate_geoms[best_idx]
            }

        diff_penalty = np.sum(
            (pred_specs[:, fixed_idxs] - target_specs[fixed_idxs])**2, axis=1
        )
        gain = np.sum(pred_specs[:, free_idxs], axis=1)
        score = gain - diff_penalty
        best_idx = np.argmax(score)

        return {
            "mode": "partial_match",
            "target_specs": target_specs,
            "pred_spec": pred_specs[best_idx],
            "geometry": candidate_geoms[best_idx]
        }

    if four_variants:
        variants = {"x.25":[0.25], "x.5":[0.5], "x.75":[0.75], "x.1":[0.0]}
        results, rel_errs_map = {}, {}
        fixed_idxs = [i for i, v in enumerate(target_specs) if not np.isnan(v)]

        for name, offs in variants.items():
            print(f"\n=== kNN Optimizing for {name} pattern ===")
            res = single_variant(offs)
            rel_err = None

            if res and res["mode"] != "no_match" and fixed_idxs:
                pred = res["pred_spec"][fixed_idxs]
                targ = target_specs[fixed_idxs]
                rel_err = np.mean(np.abs((pred - targ) / targ))
                res["rel_err"] = float(rel_err)

                if rel_err > max_rel_err:
                    
                    res = {"mode": "no_match", "rel_err": float(rel_err)}

            results[name] = res if res else {"mode": "no_match"}
            rel_errs_map[name] = rel_err if rel_err is not None else float("inf")

        valid = [k for k,v in results.items() if v.get("mode") != "no_match"]
        if not valid and fixed_idxs:
            best_variant = min(rel_errs_map, key=rel_errs_map.get)
            print(f"?? No variant satisfied max_rel_err={max_rel_err}. "
                  f"Returning best fallback: {best_variant} (rel_err={rel_errs_map[best_variant]:.2f})")
            for k in results.keys():
                if k != best_variant:
                    results[k] = {"mode": "no_match"}

        return {"target_specs": target_specs, "variants": results}

    # --- single variant mode (always return dict with variants) ---
    res = single_variant([0.0])
    if res is None:
        res = {"mode": "no_match"}
    return {"target_specs": target_specs, "variants": {"x.1": res}}





def setup_all_models(dataset_path):

    start_emx_train = time.time()
    emx_estimator_rf_model = my_emx.train_emx_estimator(dataset_path)

    print('*' * 50, '\n\n')
    start_knn_train = time.time()
    print(f'Training the KNN model')
    knn_model, knn_geom_train = my_knn.train_knn_model(dataset_path)
    print(f'Training the KNN model finished in {time.time() - start_knn_train}')
    print('*' * 50, '\n\n')
    return emx_estimator_rf_model, knn_model, knn_geom_train



import argparse
import os
import sys
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="kNN + EMX-based inductor geometry optimizer"
    )

    parser.add_argument(
        "--dataset_path",
        type=str,
        default=os.path.join(base, "DEV", "DATASETS", "spiral_ind_data.csv"),
        help="Path to the training dataset CSV"
    )

    parser.add_argument(
        "--inductance",
        type=float,
        default=1699.0,
        help="Target inductance (default: 1699.0)"
    )

    parser.add_argument(
        "--peak_q",
        type=float,
        default=None,
        help="Target peak Q (default: None)"
    )

    parser.add_argument(
        "--peak_q_freq",
        type=float,
        default=None,
        help="Target peak Q frequency (default: None)"
    )

    parser.add_argument(
        "--srf",
        type=float,
        default=None,
        help="Target SRF (default: None)"
    )

    parser.add_argument(
        "--n_neighbors",
        type=int,
        default=5000,
        help="Number of kNN candidates to evaluate (default: 5000)"
    )

    parser.add_argument(
        "--max_rel_err",
        type=float,
        default=0.1,
        help="Maximum allowed mean relative error for fixed specs in multi-variant mode (default: 0.1)"
    )

    parser.add_argument(
        "--single_variant",
        action="store_true",
        help="Run only the x.1 variant instead of all four variants"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    target_specs = [
        args.inductance if args.inductance is not None else np.nan,
        args.peak_q if args.peak_q is not None else np.nan,
        args.peak_q_freq if args.peak_q_freq is not None else np.nan,
        args.srf if args.srf is not None else np.nan,
    ]

    print("\n" + "=" * 90)
    print("kNN + EMX inductor geometry optimizer")
    print("=" * 90)
    print(f"Dataset path        : {args.dataset_path}")
    print(f"Target specs        : {target_specs}")
    print(f"n_neighbors         : {args.n_neighbors}")
    print(f"Four variants       : {not args.single_variant}")
    print(f"Max relative error  : {args.max_rel_err}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name}")
    print(f"  Partial : python {script_name} --inductance 1044 --peak_q 10")
    print(f"  Full    : python {script_name} --inductance 190 --peak_q 28 --peak_q_freq 40 --srf 110")
    print("=" * 90)

    if not os.path.exists(args.dataset_path):
        raise FileNotFoundError(f"Dataset file not found: {args.dataset_path}")

    print("\nSetting up EMX estimator and kNN models...")
    emx_estimator_rf_model, knn_model, knn_geom_train = setup_all_models(args.dataset_path)

    print("\nRunning optimization...")
    results = optimize_specs_multi_variant(
        target_specs=target_specs,
        emx_estimator_model=emx_estimator_rf_model,
        knn_model=knn_model,
        knn_train_data=knn_geom_train,
        n_neighbors=args.n_neighbors,
        four_variants=not args.single_variant,
        max_rel_err=args.max_rel_err
    )

    print("\nOptimization results:\n")
    print(results)


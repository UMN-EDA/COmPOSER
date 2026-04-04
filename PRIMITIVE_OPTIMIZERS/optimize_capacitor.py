import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from scipy.optimize import root_scalar
import argparse
import os
import sys
base = os.environ["PROJECT_HOME"]           # get the directory

# ==========================================
# 1. Train polynomial model
# ==========================================
def train_poly_model(csv_path, degree=1, model_path="mimcap_poly_model.pkl"):
    df = pd.read_csv(csv_path)
    X = df[["Length", "Width"]].values
    y = df["Capacitance"].values

    poly_model = Pipeline([
        ("poly", PolynomialFeatures(degree=degree, include_bias=False)),
        ("linreg", LinearRegression())
    ])
    poly_model.fit(X, y)

    y_pred = poly_model.predict(X)
    mae = mean_absolute_error(y, y_pred)

    # Log polynomial coefficients
    feature_names = poly_model.named_steps["poly"].get_feature_names_out(["Length", "Width"])
    coefs = poly_model.named_steps["linreg"].coef_
    intercept = poly_model.named_steps["linreg"].intercept_

    equation_terms = [f"{coef:.6e}*{name}" for coef, name in zip(coefs, feature_names)]
    equation = " + ".join(equation_terms) + f" + {intercept:.6e}"
    
    joblib.dump(poly_model, model_path)
    return poly_model


# ==========================================
# 2. Load model
# ==========================================
def load_poly_model(model_path="mimcap_poly_model.pkl"):
    return joblib.load(model_path)


# ==========================================
# 3. Export polynomial equation
# ==========================================
def export_equation(poly_model):
    poly = poly_model.named_steps["poly"]
    linreg = poly_model.named_steps["linreg"]

    feature_names = poly.get_feature_names_out(["Length", "Width"])
    coeffs = linreg.coef_
    intercept = linreg.intercept_

    equation_terms = [f"{coef:.4e}*{name}" for coef, name in zip(coeffs, feature_names)]
    equation = " + ".join(equation_terms) + f" + {intercept:.4e}"
    print("\nPolynomial fit equation:")
    print("C(L, W) ?", equation)
    return equation


# ==========================================
# 4. Predict capacitance for given L, W
# ==========================================
def predict_capacitance(poly_model, L, W):
    return poly_model.predict([[L, W]])[0]


# ==========================================
# 5. Solve inverse for aspect ratios
# ==========================================
def solve_for_aspect(C_target, AR, poly_model, W_min=4, W_max=100,
                     tol_frac=0.1, n_grid=1000):
    def f(W):
        L = AR * W
        if L < W or W < W_min or W > W_max or L < W_min or L > W_max:
            return np.nan
        return poly_model.predict([[L, W]])[0] - C_target

    solutions = []
    grid = np.linspace(W_min, W_max, n_grid)

    for i in range(len(grid) - 1):
        a, b = grid[i], grid[i + 1]
        fa, fb = f(a), f(b)
        if np.isnan(fa) or np.isnan(fb):
            continue
        if np.sign(fa) * np.sign(fb) <= 0:
            try:
                sol = root_scalar(f, bracket=[a, b], method="brentq")
                if sol.converged:
                    W_sol = sol.root
                    L_sol = AR * W_sol
                    C_pred = poly_model.predict([[L_sol, W_sol]])[0]
                    err = abs(C_pred - C_target)
                    if err <= tol_frac * C_target:
                        solutions.append({
                            "AspectRatio": AR,
                            "Length": round(L_sol, 2),
                            "Width": round(W_sol, 2),
                            "PredCap": float(f"{C_pred:.3e}"),
                            "AbsErr": float(f"{err:.3e}")
                        })
            except:
                continue

    return solutions



def find_candidates_fast(C_target, poly_model, aspect_ratios=None,
                         W_min=4, W_max=100, tol_frac=0.1):
    if aspect_ratios is None:
        aspect_ratios = [1, 1.5, 2, 2.5, 3, 3.5, 4]

    all_results = []
    best_dict = {}

    for AR in aspect_ratios:
        sols = solve_for_aspect(C_target, AR, poly_model,
                                W_min=W_min, W_max=W_max, tol_frac=tol_frac)
        if sols:
            all_results.extend(sols)
            # pick the best (lowest AbsErr) solution for this AR
            best_sol = min(sols, key=lambda x: x["AbsErr"])
            best_dict[AR] = (best_sol["Length"], best_sol["Width"], best_sol["PredCap"])

    if not all_results:
        print("?? No valid candidates found")
        return (
            pd.DataFrame(columns=["AspectRatio", "Length", "Width", "PredCap", "AbsErr"]),
            {}
        )

    df = pd.DataFrame(all_results).sort_values("AbsErr").reset_index(drop=True)
    return df, best_dict


# ==========================================
# Example run
# ==========================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Polynomial MIM capacitor model training, prediction, and inverse search"
    )

    parser.add_argument(
        "--csv_path",
        type=str,
        default=os.path.join(base, "DEV", "DATASETS", "mimcap_dataset.csv"),
        help="Path to the input CSV dataset"
    )

    parser.add_argument(
        "--degree",
        type=int,
        default=2,
        help="Polynomial degree for model fitting (default: 2)"
    )

    parser.add_argument(
        "--model_path",
        type=str,
        default=os.path.join(base, "DEV", "MODELS", "mimcap_poly_model.pkl"),
        help="Path to save the trained model (default: mimcap_poly_model.pkl)"
    )

    parser.add_argument(
        "--predict_length",
        type=float,
        default=100.0,
        help="Length used for single-point prediction (default: 100.0)"
    )

    parser.add_argument(
        "--predict_width",
        type=float,
        default=22.9,
        help="Width used for single-point prediction (default: 22.9)"
    )

    parser.add_argument(
        "--target_cap",
        type=float,
        default=505,
        help="Target capacitance for inverse search (default: 505)"
    )

    parser.add_argument(
        "--aspect_ratios",
        nargs="+",
        type=float,
        default=[1, 1.5, 2, 2.5, 3, 3.5, 4],
        help="Aspect ratios to search during inverse solve (default: 1 1.5 2 2.5 3 3.5 4)"
    )

    parser.add_argument(
        "--w_min",
        type=float,
        default=4,
        help="Minimum width for inverse search (default: 4)"
    )

    parser.add_argument(
        "--w_max",
        type=float,
        default=100,
        help="Maximum width for inverse search (default: 100)"
    )

    parser.add_argument(
        "--tol_frac",
        type=float,
        default=0.1,
        help="Allowed fractional error for inverse search (default: 0.1)"
    )

    parser.add_argument(
        "--show_top",
        type=int,
        default=15,
        help="Number of top candidate rows to print (default: 15)"
    )

    parser.add_argument(
        "--export_equation",
        action="store_true",
        help="Print the fitted polynomial equation"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 90)
    print("MIM capacitor polynomial model flow")
    print("=" * 90)
    print(f"CSV path           : {args.csv_path}")
    print(f"Polynomial degree  : {args.degree}")
    print(f"Model path         : {args.model_path}")
    print(f"Predict Length     : {args.predict_length}")
    print(f"Predict Width      : {args.predict_width}")
    print(f"Target capacitance : {args.target_cap}")
    print(f"Aspect ratios      : {args.aspect_ratios}")
    print(f"W min / W max      : {args.w_min} / {args.w_max}")
    print(f"Tolerance fraction : {args.tol_frac}")
    print(f"Top rows to print  : {args.show_top}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name}")
    print(f"  Custom  : python {script_name} --csv_path mimcap_dataset_tsmc.csv --degree 2 --predict_length 100 --predict_width 22.9 --target_cap 505")
    print("=" * 90)

    if not os.path.exists(args.csv_path):
        raise FileNotFoundError(f"CSV file not found: {args.csv_path}")

    print("\nTraining polynomial model...")
    poly_model = train_poly_model(
        csv_path=args.csv_path,
        degree=args.degree,
        model_path=args.model_path
    )
    print(f"Model saved to: {args.model_path}")

    if args.export_equation:
        export_equation(poly_model)

    print("\nRunning single-point prediction...")
    C_pred = predict_capacitance(
        poly_model,
        args.predict_length,
        args.predict_width
    )
    print(
        f"Predicted capacitance for "
        f"L={args.predict_length}, W={args.predict_width}: {C_pred:.4e} F"
    )

    print("\nRunning inverse search...")
    candidates_df, best_dict = find_candidates_fast(
        C_target=args.target_cap,
        poly_model=poly_model,
        aspect_ratios=args.aspect_ratios,
        W_min=args.w_min,
        W_max=args.w_max,
        tol_frac=args.tol_frac
    )

    print("\nCandidate geometries:\n")
    print(candidates_df.head(args.show_top))

    print("\nBest candidate per aspect ratio:\n")
    print(best_dict)


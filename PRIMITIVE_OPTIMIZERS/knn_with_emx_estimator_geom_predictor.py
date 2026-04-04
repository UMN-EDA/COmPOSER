import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.model_selection import train_test_split
from joblib import load
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import os, time
from joblib import dump
# --- Config ---
base = os.environ["PROJECT_HOME"]
MODEL_PATH = os.path.join(base, "DEV", "MODELS","emx_rf_model.pkl")
PDF_PLOT_FILE = "knn_emx_inverse_scatter_histograms.pdf"
OUTPUT_CSV = "knn_inverse_test_predictions.csv"
K_NEIGHBORS = 50

spec_cols = ["Inductance", "Peak Q", "Peak Q Freq", "SRF"]
geom_cols = ["Radius", "Width", "Spacing", "Turns"]

# ----------------------------------------------------------
# 1. Utility Functions
# ----------------------------------------------------------
def compute_metrics(y_true, y_pred):
    eps = 1e-8
    mse = mean_squared_error(y_true, y_pred)
    return {
        "r2": r2_score(y_true, y_pred),
        "mae": mean_absolute_error(y_true, y_pred),
        "mse": mse,
        "rmse": np.sqrt(mse),
        "max_ae": np.max(np.abs(y_true - y_pred)),
        "mape": np.mean(np.abs((y_true - y_pred) / (y_true + eps))),
        "smape": np.mean(2 * np.abs(y_true - y_pred) /
                         (np.abs(y_true) + np.abs(y_pred) + eps))
    }

def load_and_prepare(csv_file):
    df = pd.read_csv(csv_file)
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    df = df[
        (df['Inductance'] > 0) &
        (df["SRF"] > 25) &
        (df["Inductance"] < 4000) &
        (df["Peak Q Freq"] < df["SRF"])
    ]
    return df

def train_models(df, k_neighbors, knn_save_path="knn_model.pkl"):
    """
    Split dataset, train k-NN model, load EMX model, and save the k-NN model.

    Returns
    -------
    spec_train, geom_train, spec_test, geom_test, knn_model, emx_model
    """
    train_df, test_df = train_test_split(df, test_size=0.10, random_state=42)
    spec_train, geom_train = train_df[spec_cols].values, train_df[geom_cols].values
    spec_test, geom_test = test_df[spec_cols].values, test_df[geom_cols].values

    # Train and save k-NN model
    knn_model = NearestNeighbors(n_neighbors=k_neighbors)
    knn_model.fit(spec_train)
    dump({"knn_model": knn_model, "geom_train": geom_train}, knn_save_path)
    print(f"? k-NN model saved to {knn_save_path}")

    return spec_train, geom_train, spec_test, geom_test, knn_model

def save_plots(spec_test, best_emx_specs, pdf_file):
    with PdfPages(pdf_file) as pdf:
        plt.rcParams.update({'font.size': 14})
        for i, name in enumerate(spec_cols):
            y_true = spec_test[:, i]
            y_pred = best_emx_specs[:, i]
            metrics = compute_metrics(y_true, y_pred)
            metrics_txt = (
                f"R² = {metrics['r2']:.4f}  |  "
                f"MSE = {metrics['mse']:.2e}  |  "
                f"MAE = {metrics['mae']:.2e}  |  "
                f"RMSE = {metrics['rmse']:.2e}  |  "
                f"MaxAE = {metrics['max_ae']:.2e}\n"
                f"MAPE = {metrics['mape']*100:.2f}%  |  "
                f"SMAPE = {metrics['smape']*100:.2f}%"
            )
            fig, axes = plt.subplots(1, 2, figsize=(16, 6))
            fig.suptitle(f"{name}: Target vs Predicted\n{metrics_txt}", fontsize=12)

            ax1, ax2 = axes
            ax1.scatter(y_true, y_pred, alpha=0.6, s=10)
            lims = [min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())]
            ax1.plot(lims, lims, 'k--', alpha=0.75)
            ax1.set_xlim(lims)
            ax1.set_ylim(lims)
            ax1.set_xlabel("True " + name)
            ax1.set_ylabel("Predicted " + name)
            ax1.set_title("True vs Predicted")
            ax1.grid(True)
            ax1.set_aspect('equal', adjustable='box')

            ratio = y_true / y_pred
            ax2.hist(ratio, bins=50, edgecolor='black', alpha=0.7)
            ax2.set_title("Ratio: True / Predicted")
            ax2.set_xlabel("Error")
            ax2.set_ylabel("Frequency")
            ax2.grid(True)
            ax2.set_xlim(0.9, 1.1)

            plt.tight_layout(rect=[0, 0.03, 1, 0.92])
            pdf.savefig(fig)
            plt.close(fig)

def save_results_csv(spec_test, best_emx_specs, residuals,
                     geom_test, best_geometries, csv_file):
    export_df = pd.DataFrame({
        "True_Inductance": spec_test[:, 0],
        "True_Peak_Q": spec_test[:, 1],
        "True_Peak_Q_Freq": spec_test[:, 2],
        "True_SRF": spec_test[:, 3],
        "Pred_Inductance": best_emx_specs[:, 0],
        "Pred_Peak_Q": best_emx_specs[:, 1],
        "Pred_Peak_Q_Freq": best_emx_specs[:, 2],
        "Pred_SRF": best_emx_specs[:, 3],
        "Error_Inductance": residuals[:, 0],
        "Error_Peak_Q": residuals[:, 1],
        "Error_Peak_Q_Freq": residuals[:, 2],
        "Error_SRF": residuals[:, 3],
        "Dataset_Radius": geom_test[:, 0],
        "Dataset_Width": geom_test[:, 1],
        "Dataset_GndDist": geom_test[:, 2],
        "Dataset_Turns": geom_test[:, 3],
        "Predicted_Radius": best_geometries[:, 0],
        "Predicted_Width": best_geometries[:, 1],
        "Predicted_GndDist": best_geometries[:, 2],
        "Predicted_Turns": best_geometries[:, 3],
    })
    export_df.to_csv(csv_file, index=False)
    print(f"? Results exported to: {csv_file}")

# ----------------------------------------------------------
# 2. Core Evaluations
# ----------------------------------------------------------
def evaluate_full_test(spec_test, geom_test, geom_train, knn_model, emx_model,
                       pdf_file, csv_file, k_neighbors):
    print("? Running vectorized inference on test set...")
    start_infer = time.time()

    distances, indices = knn_model.kneighbors(spec_test)
    geom_candidates = geom_train[indices]
    N_test, k, geom_dim = geom_candidates.shape

    flat_geom_candidates = geom_candidates.reshape(-1, geom_dim)
    flat_emx_preds = emx_model.predict(flat_geom_candidates)
    emx_preds = flat_emx_preds.reshape(N_test, k, -1)

    spec_test_expanded = np.expand_dims(spec_test, axis=1)
    errors = np.linalg.norm(emx_preds - spec_test_expanded, axis=2)

    best_indices = np.argmin(errors, axis=1)
    best_geometries = geom_candidates[np.arange(N_test), best_indices]
    best_emx_specs = emx_preds[np.arange(N_test), best_indices]
    residuals = spec_test - best_emx_specs

    print(f"Total time for inferencing each inductor layout "
          f"{(time.time() - start_infer)/len(geom_test):.4f} seconds")

    save_plots(spec_test, best_emx_specs, pdf_file)
    save_results_csv(spec_test, best_emx_specs, residuals, geom_test,
                     best_geometries, csv_file)

    return best_emx_specs, best_geometries, residuals

def predict_single_spec(input_spec, knn_model, knn_train_data, emx_estimator_model):
    """
    Given one [Inductance, Peak Q, Peak Q Freq, SRF], find best geometry and specs.
    Loads both the trained k-NN model and its training geometries from disk.
    """
    print(f"Recieved inputs specs {input_spec}")

    target = np.array(input_spec, dtype=float)
    distances, indices = knn_model.kneighbors([target])
    geom_candidates = knn_train_data[indices[0]]

    preds = emx_estimator_model.predict(geom_candidates)
    errors = np.linalg.norm(preds - target, axis=1)
    best_idx = np.argmin(errors)

    best_geom = geom_candidates[best_idx]
    best_spec = preds[best_idx]
    best_error = errors[best_idx]

    return best_spec, best_geom, best_error
# ----------------------------------------------------------
# 3. Main Orchestration
# ----------------------------------------------------------
def main():
    start_time = time.time()
    df = load_and_prepare(CSV_FILE)
    spec_train, geom_train, spec_test, geom_test, knn_model, emx_model = \
        train_models(df, K_NEIGHBORS, MODEL_PATH)
    print(f"Total time to train the k-NN model {time.time() - start_time:.2f} seconds")

    # Evaluate on full test set
    best_emx_specs, best_geometries, residuals = evaluate_full_test(
        spec_test, geom_test, geom_train, knn_model, emx_model,
        PDF_PLOT_FILE, OUTPUT_CSV, K_NEIGHBORS
    )
    print("? All done. Vectorized inference + plots saved.")

    # Example: Single input query
    single_input = [190, 28, 40, 110]
    predict_single_spec(single_input, os.path.join(base, "DEV", "MODELS", "knn_model.pkl"), emx_model)

def train_knn_model(dataset_path):
    start_time = time.time()
    df = load_and_prepare(dataset_path)
    _, geom_train, _, _, knn_model = \
        train_models(df, k_neighbors=K_NEIGHBORS, knn_save_path=os.path.join(base, "DEV", "MODELS", "knn_model.pkl"))
    print(f"Total time to train the k-NN model {time.time() - start_time:.2f} seconds")
    return knn_model, geom_train

# if __name__ == "__main__":
#     main()


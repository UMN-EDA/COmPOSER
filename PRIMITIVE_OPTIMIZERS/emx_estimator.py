import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    r2_score,
    mean_squared_error,
    mean_absolute_error,
    mean_absolute_percentage_error
)
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import glob, os
from joblib import dump
from joblib import load
import numpy as np
import time
from matplotlib.ticker import ScalarFormatter, MaxNLocator

base = os.environ["PROJECT_HOME"]
import textwrap

def load_data(path):
    df = pd.read_csv(path)
    df = df.apply(pd.to_numeric, errors="coerce").astype(float)
    df = df.dropna()
    #df = df[:10000]
    df_filtered = df
    df_filtered = df_filtered[df_filtered["SRF"] > 25]
    df_filtered = df_filtered[df_filtered["Inductance"] > 0]
    df_filtered = df_filtered[df_filtered["Inductance"] < 4000]
    df_filtered = df_filtered[df_filtered["Peak Q Freq"] < df_filtered["SRF"]]
    return df_filtered

def get_models():
    models = {}
    # Random Forest
    base_rf = RandomForestRegressor(n_estimators=200, random_state=42)
    models['RandomForest'] = MultiOutputRegressor(base_rf)
    # MLP Regressor
    base_mlp = MLPRegressor(hidden_layer_sizes=(32,64, 32), activation='relu',
                            max_iter=1000, random_state=42)
    # models['MLP'] = MultiOutputRegressor(base_mlp)
    # # Polynomial Ridge
    pipe_pr = Pipeline([
        ('poly', PolynomialFeatures(degree=3, include_bias=False)),
        #('scale', StandardScaler()),
        ('ridge', Ridge(alpha=1e-6))
    ])
    # models['PolyRidge'] = MultiOutputRegressor(pipe_pr)
    return models

def apply_step_rounding(y_preds):
    y = y_preds.copy()
    y[:, 0] = np.round(y[:, 0] / 5) * 5          # Radius: nearest 5
    y[:, 1] = np.round(y[:, 1])                  # Width: nearest 1
    y[:, 2] = np.round(y[:, 2] / 5) * 5         # Gnd_dist: nearest 10
    y[:, 3] = np.round(y[:, 3] / 0.5) * 0.5       # Spacing: nearest 0.5
    y[:, 4] = np.round(y[:, 4] / 0.25) * 0.25     # Turns: nearest 0.25
    return y

def evaluate_models(X_train, X_test, y_train, y_test, models):
    results = {}
    for name, model in models.items():
        start_train  = time.time()
        model.fit(X_train, y_train)
       
        start_infer = time.time()
        y_pred = model.predict(X_test)

        y_pred_rounded = y_pred #apply_step_rounding(y_pred)

        # basic metrics
        r2    = r2_score(y_test, y_pred,           multioutput='raw_values')
        mse   = mean_squared_error(y_test, y_pred,  multioutput='raw_values')
        mae   = mean_absolute_error(y_test, y_pred, multioutput='raw_values')
        rmse  = np.sqrt(mse)
        maxae = np.max(np.abs(y_pred - y_test), axis=0)

        # rounded metrics
        r2_r      = r2_score(y_test, y_pred_rounded,           multioutput='raw_values')
        mse_r     = mean_squared_error(y_test, y_pred_rounded, multioutput='raw_values')
        mae_r     = mean_absolute_error(y_test, y_pred_rounded, multioutput='raw_values')
        rmse_r    = np.sqrt(mse_r)
        maxae_r   = np.max(np.abs(y_pred_rounded - y_test), axis=0)

        # percentage metrics
        mape      = mean_absolute_percentage_error(y_test, y_pred,           multioutput='raw_values')
        smape     = np.mean(
                      2 * np.abs(y_pred - y_test) /
                      (np.abs(y_test) + np.abs(y_pred) + 1e-8),
                      axis=0
                   )
        # rounded percentage metrics
        mape_r    = mean_absolute_percentage_error(y_test, y_pred_rounded,           multioutput='raw_values')
        smape_r   = np.mean(
                      2 * np.abs(y_pred_rounded - y_test) /
                      (np.abs(y_test) + np.abs(y_pred_rounded) + 1e-8),
                      axis=0
                   )

        results[name] = {
            'model':          model,
            'y_pred':         y_pred,
            'y_pred_rounded': y_pred_rounded,
            'r2':             r2,
            'mse':            mse,
            'mae':            mae,
            'rmse':           rmse,
            'maxae':          maxae,
            'r2_rounded':     r2_r,
            'mse_rounded':    mse_r,
            'mae_rounded':    mae_r,
            'rmse_rounded':   rmse_r,
            'maxae_rounded':  maxae_r,
            'mape':           mape,
            'smape':          smape,
            'mape_rounded':   mape_r,
            'smape_rounded':  smape_r
        }
    return results




def plot_scatter_only(
    y_test,
    results,
    target_names,
    output_pdf="emx_rf_scatter_only.pdf",
    fontsize=34,
    metrics_fontsize=28,
    fontname="Times New Roman",
):
    """
    Generate square scatter plots (one per target) for all models.
    Each plot:
        - Uses Times New Roman (fallback to DejaVu Serif)
        - Displays metrics inside the plot
        - Saves each plot on its own PDF page
        - Starts both axes from 0 with equal tick spacing
        - If tick labels are in thousands, converts them to 'k' notation
    """

    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': [fontname, 'DejaVu Serif', 'Times'],
        'font.size': metrics_fontsize - 4,
        'axes.titlesize': metrics_fontsize - 4,
        'axes.labelsize': metrics_fontsize - 4,
        'xtick.labelsize': metrics_fontsize - 4,
        'ytick.labelsize': metrics_fontsize - 4,
    })

    def k_formatter(x, pos):
        if abs(x) >= 1000:
            return f"{x/1000:.0f}k"
        return f"{x:.0f}"

    with PdfPages(output_pdf) as pdf:
        for model_name, res in results.items():
            for i, target in enumerate(target_names):
                y_true = y_test[:, i]
                y_pred = res["y_pred"][:, i]

                # Metrics
                r2, mse, mae, mape = res["r2"][i], res["mse"][i], res["mae"][i], res["mape"][i]
                metrics_text = (
                    f"R² = {r2:.5f}\n"
                    f"MSE = {mse:.2e}\n"
                    f"MAE = {mae:.2e}\n"
                    f"MAPE = {100*mape:.2f}%"
                )

                fig, ax = plt.subplots(figsize=(6, 6))
                ax.scatter(y_true, y_pred, s=12, alpha=0.6)

                mn = 0
                mx = max(y_true.max(), y_pred.max()) * 1.05
                ax.plot([mn, mx], [mn, mx], '--k', linewidth=1)
                ax.set_xlim(mn, mx)
                ax.set_ylim(mn, mx)
                ax.set_aspect('equal', adjustable='box')

                ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
                ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

                # Apply 'k' formatter only when necessary
                if mx >= 1000:
                    ax.xaxis.set_major_formatter(plt.FuncFormatter(k_formatter))
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(k_formatter))
                else:
                    ax.xaxis.set_major_formatter(ScalarFormatter(useMathText=True))
                    ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))

                ax.set_xlabel(f"True {target}")
                ax.set_ylabel(f"Predicted {target}")
                # ---- Title wrapping into two lines if too long ----
                # ---- Dynamically wrap title according to plot width ----
                title = f"EM Surrogate model \n {target} Prediction"
               
                ax.set_title(title)


                ax.text(
                    0.97, 0.03, metrics_text,
                    transform=ax.transAxes,
                    fontsize=metrics_fontsize,
                    fontname=fontname,
                    verticalalignment="bottom",
                    horizontalalignment="right",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="black", alpha=0.8)
                )

                ax.grid(True, linestyle=':', linewidth=0.7)
                plt.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)

                print(f"Saved scatter plot for {model_name} - {target}")

    print(f"All scatter plots saved to '{output_pdf}'")


def plot_results(y_test, results, target_names, output_pdf, clean_dir="clean_pages"):
    """
    Save plots to:
      1) A combined PDF with metrics header text.
      2) Separate single-page PDFs without header text (inside clean_dir).
    """
    plt.rcParams.update({'font.size': 10})
    os.makedirs(clean_dir, exist_ok=True)

    with PdfPages(output_pdf) as pdf:
        for name, res in results.items():
            for i, target in enumerate(target_names):
                # metrics
                r2, mse, mae, rmse, maxae = (res['r2'][i], res['mse'][i],
                                             res['mae'][i], res['rmse'][i],
                                             res['maxae'][i])
                r2r, mse_r, mae_r, rmse_r, maxae_r = (res['r2_rounded'][i], res['mse_rounded'][i],
                                                      res['mae_rounded'][i], res['rmse_rounded'][i],
                                                      res['maxae_rounded'][i])
                mape, smape = res['mape'][i], res['smape'][i]
                mape_r, smape_r = res['mape_rounded'][i], res['smape_rounded'][i]

                metrics_text = (
                    f"Raw:      R²={r2:.5f}, MSE={mse:.2e}, MAE={mae:.2e}, "
                    f"RMSE={rmse:.2e}, MaxAE={maxae:.2e}\n"
                    f"Rounded:  R²={r2r:.3f}, MSE={mse_r:.2e}, MAE={mae_r:.2e}, "
                    f"RMSE={rmse_r:.2e}, MaxAE={maxae_r:.2e}\n"
                    f"Percent:  MAPE={100*mape:.2f}%, SMAPE={100*smape:.2f}%\n"
                    f"PctRnd:   MAPE={100*mape_r:.2f}%, SMAPE={100*smape_r:.2f}%"
                )

                # ------------- Full version with header -----------------
                fig, axes = plt.subplots(1, 2, figsize=(8, 6))
                fig.suptitle(f"{name} ? {target}\n" + metrics_text, fontsize=10)

                ax1 = axes[0]
                ax1.scatter(y_test[:, i], res['y_pred'][:, i], s=8, alpha=0.5)
                mn, mx = y_test[:, i].min(), y_test[:, i].max()
                ax1.plot([mn, mx], [mn, mx], '--k')
                ax1.set_xlabel(f"True {target}")
                ax1.set_ylabel(f"Pred {target}")
                ax1.set_title("EMX of RF predicted layout vs Target EMX")
                ax1.grid(True)

                ax2 = axes[1]
                resid = res['y_pred'][:, i] / y_test[:, i]
                ax2.hist(resid, bins=100, edgecolor='black', alpha=0.7)
                ax2.set_xlabel("Pred / True")
                ax2.set_title("Raw Ratio")
                ax2.set_xlim(0.9, 1.1)

                plt.tight_layout(rect=[0, 0, 1, 0.88])
                pdf.savefig(fig)
                plt.close(fig)


                # --------- Clean version with larger fonts ----------
                clean_fontsize = 16
                plt.rcParams.update({'font.size': clean_fontsize})
                fig_clean, axes_clean = plt.subplots(1, 2, figsize=(12, 6))

                ax1c = axes_clean[0]
                ax1c.scatter(y_test[:, i], res['y_pred'][:, i], s=12, alpha=0.6)
                ax1c.plot([mn, mx], [mn, mx], '--k')
                ax1c.set_xlabel(f"True {target}", fontsize=clean_fontsize)
                ax1c.set_ylabel(f"Pred {target}", fontsize=clean_fontsize)
                ax1c.set_title("EMX of RF predicted layout vs Target EMX",
                               fontsize=clean_fontsize)
                ax1c.tick_params(labelsize=clean_fontsize)
                ax1c.grid(True)

                ax2c = axes_clean[1]
                ax2c.hist(resid, bins=100, edgecolor='black', alpha=0.7)
                ax2c.set_xlabel("Pred / True", fontsize=clean_fontsize)
                ax2c.set_title("Raw Ratio", fontsize=clean_fontsize)
                ax2c.tick_params(labelsize=clean_fontsize)
                ax2c.set_xlim(0.9, 1.1)

                plt.tight_layout()
                clean_path = os.path.join(clean_dir, f"{name}_{target}.pdf")
                fig_clean.savefig(clean_path)
                plt.close(fig_clean)
                print(f"Saved clean plot to {clean_path}")

                # reset rcParams so combined PDF font size stays small
                plt.rcParams.update({'font.size': 10})


def export_test_results_csv(X_test, y_test, results, feature_cols, target_names, output_csv):
    # build DataFrame of inputs
    df_out = pd.DataFrame(X_test, columns=feature_cols)

    for name, res in results.items():
        preds = res['y_pred']
        for i, tgt in enumerate(target_names):
            tgt_clean = tgt.lower().replace(' ', '_')
            df_out[f"{tgt_clean}_true"] = y_test[:, i]
            df_out[f"{tgt_clean}_{name.lower()}"] = preds[:, i]

        # Only write for one model (assumes same y_test across all)
        break

    # write to CSV
    df_out.to_csv(output_csv, index=False)
    print(f"Test inputs and predictions written to '{output_csv}'")


def train_emx_estimator(dataset_path):
    """
    Train or load a RandomForest-based EMX estimator.
    Always evaluates the model on the current dataset (even if already trained).
    Fully backward-compatible with existing evaluate_models() implementation.
    """
    pkl_file = os.path.join(base, "DEV", "MODELS","emx_rf_model.pkl")

    # --- Load and clean data ---
    df = load_data(dataset_path)
    target_names = ["Inductance", "Peak Q", "Peak Q Freq", "SRF"]
    feature_cols = ["Radius", "Width", "Spacing", "Turns"]
    X = df[feature_cols].values
    y = df[target_names].values

    # --- Train/test split ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # --- Case 1: model already trained ---
    if os.path.exists(pkl_file):

        rf_model = load(pkl_file)
        models = {"RandomForest": rf_model}

    # --- Case 2: train new model ---
    else:

        models = get_models()  # returns dict of model objects
        results = evaluate_models(X_train, X_test, y_train, y_test, models)

        if "RandomForest" in results:
            dump(results["RandomForest"]["model"], pkl_file)

            rf_model = results["RandomForest"]["model"]
        else:
            rf_model = models["RandomForest"]

        # override models dict for uniform re-evaluation
        models = {"RandomForest": rf_model}

    # --- Always re-evaluate current model ---
    evaluate = False
    if evaluate == True:

        results = evaluate_models(X_train, X_test, y_train, y_test, models)

        # --- Log detailed metrics ---
        for name, res in results.items():

            for i, tgt in enumerate(["Inductance", "Peak Q", "Peak Q Freq", "SRF"]):
                print(
                    f"  {tgt:<20} | "
                    f"R²={res['r2'][i]:.3f}, R²_rounded={res['r2_rounded'][i]:.3f}, "
                    f"MSE={res['mse'][i]:.3e}, MSE_rounded={res['mse_rounded'][i]:.3e}, "
                    f"MAE={res['mae'][i]:.3e}, MAE_rounded={res['mae_rounded'][i]:.3e}, "
                    f"RMSE={res['rmse'][i]:.3e}, RMSE_rounded={res['rmse_rounded'][i]:.3e}, "
                    f"MaxAE={res['maxae'][i]:.3e}, MaxAE_rounded={res['maxae_rounded'][i]:.3e}, "
                    f"MAPE={100*res['mape'][i]:.2f}%, MAPE_rounded={100*res['mape_rounded'][i]:.2f}%, "
                    f"SMAPE={100*res['smape'][i]:.2f}%, SMAPE_rounded={100*res['smape_rounded'][i]:.2f}%"
                )

        # --- Always save plots ---
       
        plot_results(y_test, results, target_names, "emx_model_using_RF.pdf")
        #logger.info("Saved comparison plots to 'emx_model_using_RF.pdf'")
            
        # --- Import and call scatter plotting function ---
        plot_scatter_only(
            y_test=y_test,
            results=results,
            target_names=["Inductance", "Peak Q", "Peak Q Freq", "SRF"],
            output_pdf="rf_emx_scatter_plots.pdf",  # output file name
            fontsize=18,                             # global font size control
            fontname="DejaVu Serif"
        )


    return models["RandomForest"]



def infer_emx_model(input_array, emx_estimator_model):
    """
    Perform inference using the trained RandomForest model.

    Args:
        input_array (np.ndarray): Input features, shape = (n_samples, n_features)
        model_path (str): Path to the saved RandomForest model (.pkl)

    Returns:
        np.ndarray: Predicted output values
    """


    if isinstance(input_array, list):
        input_array = np.array(input_array, dtype=float)

    if input_array.ndim == 1:
        input_array = input_array.reshape(1, -1)

    preds = emx_estimator_model.predict(input_array)
    # print(preds)
    return preds



if __name__ == "__main__":
    start_time = time.time()
    train_emx_estimator("spiral_gnd_fixed.csv")
    print(f"Total time to train RF EMX Surrogate model {time.time() - start_time} seconds")
#     #infer_emx_model([100, 20, 10, 150])

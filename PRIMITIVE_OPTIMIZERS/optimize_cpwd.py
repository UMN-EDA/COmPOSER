import pandas as pd
import numpy as np
from sklearn.neighbors import KNeighborsRegressor
from sklearn.manifold import TSNE
import plotly.express as px
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import argparse
import os
import sys
base = os.environ["PROJECT_HOME"]           # get the directory
# =====================================================
# Train kNN model
# =====================================================
def train_knn(csv_path="cpwd_data.csv", n_neighbors=50):
    """
    Train a kNN regressor on cpwd_data.csv for predicting [Length, Width, Gap]
    from [beta_l, Char_Imp].
    
    Returns:
        knn: trained model
        df: full dataframe for plotting
    """
    df = pd.read_csv(csv_path)
    X = df[["beta_l", "Char_Imp"]].values
    y = df[["Length", "Width", "Gap"]].values
    
    knn = KNeighborsRegressor(n_neighbors=n_neighbors)
    knn.fit(X, y)
    print(f"Successfully trained CPWD knn model")
    return knn, df


# =====================================================
# Predict geometries for N inputs
# =====================================================
def predict_CPWD_geometries(knn, query_array):
    """
    Predict geometries (Length, Width, Gap) for multiple inputs.
    
    Args:
        knn: trained KNeighborsRegressor model
        query_array: numpy array of shape (N, 2) where each row is [beta_l, Char_Imp]
    
    Returns:
        numpy array of shape (N, 3) with columns [Length, Width, Gap]
    """
    query_array = np.asarray(query_array)
    if query_array.ndim != 2 or query_array.shape[1] != 2:
        raise ValueError("Input must be of shape (N, 2): [[beta_l, Char_Imp], ...]")
    
    return knn.predict(query_array)


# =====================================================
# t-SNE visualization
# =====================================================
def plot_tsne_with_queries(df, query_array, outputs, html_file="tsne_plot.html", pdf_file="tsne_plot.pdf"):
    """
    Generate t-SNE visualization of dataset + query points.
    
    Args:
        df: dataframe with columns ["Length","Width","Gap","Char_Imp","beta_l","root_er"]
        query_array: (N,2) array of [beta_l, Char_Imp]
        outputs: (N,3) array of [Length, Width, Gap] predictions
        html_file: filename for interactive plotly output
        pdf_file: filename for static PDF plot
    """
    # --- t-SNE embedding on dataset
    tsne = TSNE(n_components=2, random_state=42, perplexity=min(30, len(df)//5))
    emb = tsne.fit_transform(df[["beta_l", "Char_Imp"]].values)
    df_vis = df.copy()
    df_vis["x"] = emb[:,0]
    df_vis["y"] = emb[:,1]
    df_vis["Type"] = "Dataset"
    
    # Add query points
    query_df = pd.DataFrame({
        "beta_l": query_array[:,0],
        "Char_Imp": query_array[:,1],
        "Length": outputs[:,0],
        "Width": outputs[:,1],
        "Gap": outputs[:,2],
        "root_er": np.nan,
        "Type": "Query"
    })
    # place query at mean of dataset embedding for display (or recompute with tsne separately if needed)
    query_df["x"] = np.mean(emb[:,0]) + np.random.randn(len(query_df))*0.01
    query_df["y"] = np.mean(emb[:,1]) + np.random.randn(len(query_df))*0.01
    
    all_vis = pd.concat([df_vis, query_df], ignore_index=True)

    # --- Interactive Plotly
    fig = px.scatter(
        all_vis, x="x", y="y", color="Type", symbol="Type",
        hover_data=["Length","Width","Gap","Char_Imp","beta_l","root_er"],
        title="t-SNE visualization with queries"
    )
    fig.write_html(html_file)
    print(f"Interactive t-SNE plot saved to {html_file}")

    # --- Static PDF with Matplotlib
    with PdfPages(pdf_file) as pdf:
        plt.figure(figsize=(8,6))
        plt.scatter(df_vis["x"], df_vis["y"], c="gray", s=20, label="Dataset", alpha=0.5)
        plt.scatter(query_df["x"], query_df["y"], c="red", s=60, label="Query", marker="X")
        plt.legend()
        plt.title("t-SNE visualization with queries")
        plt.xlabel("t-SNE 1")
        plt.ylabel("t-SNE 2")
        pdf.savefig()
        plt.close()
    print(f"Static t-SNE plot saved to {pdf_file}")


# =====================================================
# Example usage
# =====================================================


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train a CPWD kNN model, predict geometries for query points, and generate t-SNE plots."
    )

    parser.add_argument(
        "--csv-path",
        type=str,
        default=os.path.join(base, "DEV", "DATASETS", "cpwd_data.csv"),
        help="Path to the CPWD dataset CSV file. Default: cpwd_data.csv"
    )

    parser.add_argument(
        "--n-neighbors",
        type=int,
        default=500,
        help="Number of neighbors for KNeighborsRegressor. Default: 500"
    )

    parser.add_argument(
        "--beta-l",
        type=float,
        nargs="+",
        default=[0.023],
        help="One or more beta_l query values. Default: 0.023"
    )

    parser.add_argument(
        "--char-imp",
        type=float,
        nargs="+",
        default=[18],
        help="One or more Char_Imp query values. Default: 18"
    )

    parser.add_argument(
        "--html-file",
        type=str,
        default="tsne_with_queries.html",
        help="Output HTML file for interactive t-SNE plot. Default: tsne_with_queries.html"
    )

    parser.add_argument(
        "--pdf-file",
        type=str,
        default="tsne_with_queries.pdf",
        help="Output PDF file for static t-SNE plot. Default: tsne_with_queries.pdf"
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if len(args.beta_l) != len(args.char_imp):
        raise ValueError(
            f"Number of beta_l values ({len(args.beta_l)}) must match "
            f"number of Char_Imp values ({len(args.char_imp)})."
        )

    query_points = np.column_stack((args.beta_l, args.char_imp))

    knn_model, df = train_knn(args.csv_path, n_neighbors=args.n_neighbors)

    print(query_points)
    results = predict_CPWD_geometries(knn_model, query_points)
    print(results)

    #plot_tsne_with_queries(
    #    df,
    #    query_points,
    #    results,
    #    html_file=args.html_file,
    #    pdf_file=args.pdf_file
    #)


if __name__ == "__main__":
    main()


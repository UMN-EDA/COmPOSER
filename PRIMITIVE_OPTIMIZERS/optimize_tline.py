import pandas as pd
import numpy as np
from sklearn.manifold import TSNE
from sklearn.neighbors import NearestNeighbors
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import argparse
base = os.environ["PROJECT_HOME"]           # get the directory


def optimize_tline(df, input_col="Inductance",
                 target_cols=["Length","Width"],
                 n_neighbors=3, perplexity=30, random_state=42,
                 query_point=None, out_html="tsne_knn_plot.html",
                 make_plot=False):
    """
    Predict (Length, Width) from Inductance using kNN.
    Instead of averaging neighbors, selects the neighbor with minimum Length.
    If make_plot=True, also generates and saves a t-SNE visualization.
    """


    # Embedding (for visualization only)
    if make_plot:
        X_embed = df[["Length","Width","Inductance","Peak Q"]].values
        tsne = TSNE(n_components=2, perplexity=perplexity, random_state=random_state)
        embeddings = tsne.fit_transform(X_embed)
        df["TSNE1"], df["TSNE2"] = embeddings[:,0], embeddings[:,1]

    # Train neighbors on input -> targets
    X_train = df[[input_col]].values
    nbrs = NearestNeighbors(n_neighbors=n_neighbors).fit(X_train)

    pred_length, pred_width = None, None

    if query_point is not None:
        # Find neighbors of the query
        distances, indices = nbrs.kneighbors([[query_point]])
        neighbor_rows = df.iloc[indices[0]]

        # Select the neighbor with minimum Length
        best_idx = neighbor_rows["Length"].idxmin()
        best_row = df.loc[best_idx]
        pred_length, pred_width, pred_ind = best_row["Length"], best_row["Width"], best_row["Inductance"]

        if make_plot:
            # Base scatter
            fig = px.scatter(
                df, x="TSNE1", y="TSNE2",
                hover_data=["Length","Width","Inductance","Peak Q"],
                title="t-SNE (Prediction: Inductance ? Length, Width, minimizing Length)"
            )

            # Place query near neighbors (average position)
            qx, qy = neighbor_rows[["TSNE1","TSNE2"]].mean(axis=0)

            # Add predicted point
            fig.add_trace(go.Scatter(
                x=[qx], y=[qy],
                mode="markers+text",
                text=[f"Pred: L={pred_length:.2f}, W={pred_width:.2f}, Ind={query_point}"],
                textposition="top center",
                marker=dict(color="red", size=14, symbol="star"),
                name="Predicted (Min Length)"
            ))

            # Add neighbors
            neighbor_labels = [
                f"Neighbor {i+1}: Length={row['Length']}, Width={row['Width']}, "
                f"Ind={row['Inductance']}, Q={row['Peak Q']}"
                for i, row in neighbor_rows.iterrows()
            ]
            fig.add_trace(go.Scatter(
                x=neighbor_rows["TSNE1"], y=neighbor_rows["TSNE2"],
                mode="markers+text",
                text=[f"N{i+1}" for i in range(len(neighbor_rows))],
                textposition="top center",
                marker=dict(color="green", size=10, symbol="diamond"),
                name="Nearest Neighbors",
                hovertext=neighbor_labels,
                hoverinfo="text"
            ))

            fig.write_html(out_html)
            print(f"? Interactive plot saved to {out_html}")
        print(f"Proposed TLine dimensions {pred_length, pred_width}")
    return pred_length, pred_width, pred_ind


def parse_args():
    parser = argparse.ArgumentParser(
        description="kNN-based T-line dimension predictor from inductance"
    )

    parser.add_argument(
        "--csv_path",
        type=str,
        default=os.path.join(base, "DEV", "DATASETS", "tline_data.csv"),
        help="Path to the input CSV dataset"
    )

    parser.add_argument(
        "--input_col",
        type=str,
        default="Inductance",
        help="Input column used for kNN search (default: Inductance)"
    )

    parser.add_argument(
        "--target_cols",
        nargs="+",
        default=["Length", "Width"],
        help="Target columns to predict (default: Length Width)"
    )

    parser.add_argument(
        "--n_neighbors",
        type=int,
        default=3,
        help="Number of nearest neighbors to use (default: 3)"
    )

    parser.add_argument(
        "--perplexity",
        type=float,
        default=30,
        help="t-SNE perplexity for visualization (default: 30)"
    )

    parser.add_argument(
        "--random_state",
        type=int,
        default=42,
        help="Random seed for t-SNE (default: 42)"
    )

    parser.add_argument(
        "--query_point",
        type=float,
        default=100.0,
        help="Query inductance value for prediction (default: 100.0)"
    )

    parser.add_argument(
        "--out_html",
        type=str,
        default="tsne_knn_plot.html",
        help="Output HTML file for the t-SNE plot (default: tsne_knn_plot.html)"
    )

    parser.add_argument(
        "--make_plot",
        action="store_true",
        help="Generate and save the interactive t-SNE plot"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    script_name = os.path.basename(sys.argv[0])

    print("\n" + "=" * 90)
    print("kNN-based T-line optimizer")
    print("=" * 90)
    print(f"CSV path        : {args.csv_path}")
    print(f"Input column    : {args.input_col}")
    print(f"Target columns  : {args.target_cols}")
    print(f"n_neighbors     : {args.n_neighbors}")
    print(f"Perplexity      : {args.perplexity}")
    print(f"Random state    : {args.random_state}")
    print(f"Query point     : {args.query_point}")
    print(f"Output HTML     : {args.out_html}")
    print(f"Make plot       : {args.make_plot}")
    print()
    print("Example runs:")
    print(f"  Default : python {script_name}")
    print(f"  Custom  : python {script_name} --csv_path results_tline.csv --query_point 120 --n_neighbors 5 --make_plot")
    print("=" * 90)

    if not os.path.exists(args.csv_path):
        raise FileNotFoundError(f"CSV file not found: {args.csv_path}")

    print("\nReading dataset...")
    df = pd.read_csv(args.csv_path)

    print("\nRunning T-line optimization...")
    pred_length, pred_width, pred_ind = optimize_tline(
        df=df,
        input_col=args.input_col,
        target_cols=args.target_cols,
        n_neighbors=args.n_neighbors,
        perplexity=args.perplexity,
        random_state=args.random_state,
        query_point=args.query_point,
        out_html=args.out_html,
        make_plot=args.make_plot
    )

    print("\nDone.")
    print(f"Predicted Length     : {pred_length}")
    print(f"Predicted Width      : {pred_width}")
    print(f"Matched Inductance   : {pred_ind}")
    if args.make_plot:
        print(f"Plot saved to        : {args.out_html}")


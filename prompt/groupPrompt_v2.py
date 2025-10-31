import argparse
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import os
import numpy as np
from collections import Counter


def extract_representative_keywords(prompts, top_n=10):
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=1000)
    tfidf_matrix = vectorizer.fit_transform(prompts)
    tfidf_scores = tfidf_matrix.mean(axis=0).A1
    feature_names = vectorizer.get_feature_names_out()

    top_indices = np.argsort(tfidf_scores)[::-1][:top_n]
    top_keywords = [feature_names[i] for i in top_indices]
    return ", ".join(top_keywords)


def auto_estimate_clusters(n_samples):
    # Elbow rule-of-thumb: sqrt(n/2)
    return max(2, int(np.sqrt(n_samples / 2)))


def main():
    parser = argparse.ArgumentParser(description="Cluster image prompts and summarize them")
    parser.add_argument("--csv", required=True, help="Path to the metadata CSV file")
    parser.add_argument("-min", "--min_images", type=int, default=10, help="Minimum number of images per group")
    parser.add_argument("-max","--max_images", type=int, default=40, help="Maximum number of images per group")
    parser.add_argument("-c", "--clusters", type=int, default=None, help="Number of clusters (optional)")
    parser.add_argument("-o", "--output", type=str, default="grouped_prompt_summary.csv", help="Output CSV filename")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        print("❌ CSV file not found:", args.csv)
        return

    df = pd.read_csv(args.csv)
    if "positive_prompt" not in df.columns or "filename" not in df.columns:
        print("❌ CSV must contain 'positive_prompt' and 'filename' columns")
        return

    print("✅ Loaded", len(df), "rows from", args.csv)

    vectorizer = TfidfVectorizer(stop_words="english", max_features=1000)
    X = vectorizer.fit_transform(df["positive_prompt"])

    n_clusters = args.clusters or auto_estimate_clusters(len(df))
    print(f"🔍 Clustering into {n_clusters} groups...")

    # kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=20)
    df["cluster"] = kmeans.fit_predict(X)

    cluster_counts = df["cluster"].value_counts()
    valid_clusters = cluster_counts[(cluster_counts >= args.min_images) & (cluster_counts <= args.max_images)].index

    print(f"📦 Found {len(valid_clusters)} valid clusters between {args.min_images}-{args.max_images} images")

    summary_rows = []
    for i, cluster_id in enumerate(valid_clusters, start=1):
        group = df[df["cluster"] == cluster_id]
        keywords_summary = extract_representative_keywords(group["positive_prompt"].tolist(), top_n=50)
        filenames = group["filename"].tolist()
        filename_joined = "|".join(filenames)

        summary_rows.append({
            "group_index": i,
            "representative_prompt": keywords_summary,
            "image_filenames": filename_joined
        })

    summary_df = pd.DataFrame(summary_rows)
    out_path = os.path.join(os.path.dirname(args.csv), args.output)
    summary_df.to_csv(out_path, index=False)
    print("✅ Done! Summary saved to:", out_path)


if __name__ == "__main__":
    main()
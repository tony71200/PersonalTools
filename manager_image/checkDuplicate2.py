"""
Duplicate image checker with optional GPU acceleration.

Input: folder path.
Output: duplicate groups, folder containing duplicates, and duplicate counts.

This version keeps the original hybrid scoring idea:
- image score: hash, SSIM, average color, brightness
- metadata score: embedded EXIF/PIL metadata text

New in this file:
- detects whether PyTorch CUDA GPU support is available
- lets the user choose CPU or GPU when a GPU is available
- uses GPU tensors for pair filtering and batched SSIM where possible
- falls back to CPU automatically if GPU dependencies are missing
"""

import itertools
import os
import shutil
import sys
from collections import defaultdict
from difflib import SequenceMatcher

import imagehash
import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS
from scipy.spatial.distance import pdist
from skimage.metrics import structural_similarity as ssim
from tqdm import tqdm

try:
    import torch
    import torch.nn.functional as F
except ImportError:
    torch = None
    F = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".gif"}
SSIM_SIZE = (128, 128)
SSIM_BATCH_SIZE = 128
PAIR_FILTER_CHUNK_SIZE = 200_000


class UnionFind:
    """Union-Find data structure to group duplicates into connected components."""

    def __init__(self, elements):
        self.parent = {el: el for el in elements}

    def find(self, el):
        root = el
        while self.parent[root] != root:
            root = self.parent[root]

        curr = el
        while curr != root:
            nxt = self.parent[curr]
            self.parent[curr] = root
            curr = nxt
        return root

    def union(self, el1, el2):
        root1 = self.find(el1)
        root2 = self.find(el2)
        if root1 != root2:
            self.parent[root1] = root2


def get_cuda_device():
    """Return a CUDA device when PyTorch can use one, otherwise None."""
    if torch is None:
        return None
    try:
        if torch.cuda.is_available():
            return torch.device("cuda")
    except Exception:
        return None
    return None


def choose_processing_device():
    """Ask the user whether to use GPU when a CUDA GPU is available."""
    cuda_device = get_cuda_device()
    if cuda_device is None:
        if torch is None:
            print("GPU check: PyTorch is not installed. Using CPU.")
        else:
            print("GPU check: No CUDA-capable GPU detected by PyTorch. Using CPU.")
        return "cpu"

    gpu_name = torch.cuda.get_device_name(cuda_device)
    print(f"GPU detected: {gpu_name}")
    while True:
        choice = input("Choose processing device: [G]PU or [C]PU (default GPU): ").strip().lower()
        if choice in ("", "g", "gpu"):
            print("Using GPU for pair filtering and SSIM batches.")
            return "gpu"
        if choice in ("c", "cpu"):
            print("Using CPU.")
            return "cpu"
        print("Invalid choice. Enter G for GPU or C for CPU.")


def extract_image_metadata(image_path):
    """Extract embedded image metadata from EXIF and the PIL info dictionary."""
    metadata_text = []
    try:
        with Image.open(image_path) as img:
            if hasattr(img, "_getexif"):
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag_name = TAGS.get(tag_id, str(tag_id))
                        if isinstance(value, (str, int, float)):
                            metadata_text.append(f"{tag_name}: {value}")
                        elif isinstance(value, bytes):
                            try:
                                metadata_text.append(f"{tag_name}: {value.decode('utf-8', errors='ignore')}")
                            except Exception:
                                pass

            if hasattr(img, "info") and img.info:
                for key, value in img.info.items():
                    if key not in ["exif", "icc_profile", "photoshop", "xmp"]:
                        if isinstance(value, (str, int, float)):
                            metadata_text.append(f"{key}: {value}")
                        elif isinstance(value, bytes):
                            try:
                                metadata_text.append(f"{key}: {value.decode('utf-8', errors='ignore')}")
                            except Exception:
                                pass
    except Exception as e:
        print(f"Warning: Could not extract metadata from {image_path}: {e}")

    if metadata_text:
        return "\n".join(metadata_text).strip()
    return None


def get_image_features(image_path):
    """
    Extract pHash, dHash, average color, average brightness, and a resized
    grayscale array for SSIM.
    """
    try:
        with Image.open(image_path) as img:
            phash_val = imagehash.phash(img)
            dhash_val = imagehash.dhash(img)

            img_rgb = img.convert("RGB")
            avg_color = img_rgb.resize((1, 1)).getpixel((0, 0))

            img_gray = img.convert("L")
            avg_brightness = img_gray.resize((1, 1)).getpixel((0, 0))
            gray_array_128 = np.array(img_gray.resize(SSIM_SIZE), dtype=np.uint8)

            return phash_val, dhash_val, avg_color, avg_brightness, gray_array_128
    except Exception as e:
        print(f"Warning: Could not extract features for image {image_path}: {e}")
        return None


def scan_directory(folder_path):
    """Recursively scan a directory for image files."""
    image_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            _, ext = os.path.splitext(file)
            if ext.lower() in IMAGE_EXTENSIONS:
                image_files.append(os.path.normpath(os.path.join(root, file)))
    return image_files


def build_feature_matrices(valid_images, image_data):
    """Convert extracted features to arrays used by CPU and GPU paths."""
    p_hashes = np.array([image_data[img][0][0].hash.flatten() for img in valid_images], dtype=np.float32)
    d_hashes = np.array([image_data[img][0][1].hash.flatten() for img in valid_images], dtype=np.float32)
    colors = np.array([image_data[img][0][2] for img in valid_images], dtype=np.float32)
    brightness = np.array([[image_data[img][0][3]] for img in valid_images], dtype=np.float32)
    gray_images = np.stack([image_data[img][0][4] for img in valid_images]).astype(np.float32)
    has_metadata = np.array([image_data[img][1] is not None for img in valid_images], dtype=bool)
    return p_hashes, d_hashes, colors, brightness, gray_images, has_metadata


def filter_pairs_cpu(p_hashes, d_hashes, colors, brightness, has_metadata, threshold, img_weight, meta_weight):
    """Use NumPy/SciPy to remove pairs that cannot reach the threshold."""
    n = len(p_hashes)
    total_comparisons = (n * (n - 1)) // 2

    print("Calculating distances using CPU matrices (Hash, Color, Brightness)...")
    p_dist = pdist(p_hashes, metric="cityblock")
    d_dist = pdist(d_hashes, metric="cityblock")
    color_dist = pdist(colors, metric="euclidean")
    bright_dist = pdist(brightness, metric="euclidean")

    phash_sim = 1.0 - (p_dist / 64.0)
    dhash_sim = 1.0 - (d_dist / 64.0)
    hash_sim = 0.5 * phash_sim + 0.5 * dhash_sim

    max_rgb_dist = (255**2 + 255**2 + 255**2) ** 0.5
    color_sim = 1.0 - (color_dist / max_rgb_dist)
    bright_sim = 1.0 - (bright_dist / 255.0)

    base_image_sim = (0.50 * hash_sim) + (0.15 * color_sim) + (0.05 * bright_sim)
    pairs = np.array(list(itertools.combinations(range(n), 2)), dtype=np.int32)
    pair_has_meta = has_metadata[pairs[:, 0]] & has_metadata[pairs[:, 1]]

    max_possible_image_sim = base_image_sim + 0.30
    max_final_score = np.where(
        pair_has_meta,
        (img_weight * max_possible_image_sim) + (meta_weight * 1.0),
        max_possible_image_sim,
    )

    candidates = np.where(max_final_score >= threshold)[0]
    print(f"Matrix filtering successful: Removed {total_comparisons - len(candidates)} pairs.")
    return pairs[candidates], base_image_sim[candidates], pair_has_meta[candidates]


def filter_pairs_gpu(p_hashes, d_hashes, colors, brightness, has_metadata, threshold, img_weight, meta_weight):
    """Use CUDA tensors to remove pairs that cannot reach the threshold."""
    n = len(p_hashes)
    total_comparisons = (n * (n - 1)) // 2
    device = torch.device("cuda")

    print("Calculating distances using GPU tensors (Hash, Color, Brightness)...")
    p_t = torch.as_tensor(p_hashes, device=device)
    d_t = torch.as_tensor(d_hashes, device=device)
    c_t = torch.as_tensor(colors, device=device)
    b_t = torch.as_tensor(brightness.reshape(-1), device=device)
    m_t = torch.as_tensor(has_metadata, device=device)
    pair_indices = torch.combinations(torch.arange(n, device=device), r=2)

    candidate_chunks = []
    base_chunks = []
    meta_chunks = []
    max_rgb_dist = (255**2 + 255**2 + 255**2) ** 0.5

    for start in range(0, total_comparisons, PAIR_FILTER_CHUNK_SIZE):
        end = min(start + PAIR_FILTER_CHUNK_SIZE, total_comparisons)
        idx = pair_indices[start:end]
        i = idx[:, 0]
        j = idx[:, 1]

        p_dist = torch.sum(torch.abs(p_t[i] - p_t[j]), dim=1)
        d_dist = torch.sum(torch.abs(d_t[i] - d_t[j]), dim=1)
        color_dist = torch.linalg.vector_norm(c_t[i] - c_t[j], dim=1)
        bright_dist = torch.abs(b_t[i] - b_t[j])

        phash_sim = 1.0 - (p_dist / 64.0)
        dhash_sim = 1.0 - (d_dist / 64.0)
        hash_sim = 0.5 * phash_sim + 0.5 * dhash_sim
        color_sim = 1.0 - (color_dist / max_rgb_dist)
        bright_sim = 1.0 - (bright_dist / 255.0)
        base_image_sim = (0.50 * hash_sim) + (0.15 * color_sim) + (0.05 * bright_sim)

        pair_has_meta = m_t[i] & m_t[j]
        max_possible_image_sim = base_image_sim + 0.30
        max_final_score = torch.where(
            pair_has_meta,
            (img_weight * max_possible_image_sim) + (meta_weight * 1.0),
            max_possible_image_sim,
        )
        keep = max_final_score >= threshold

        if torch.any(keep):
            candidate_chunks.append(idx[keep].detach().cpu().numpy().astype(np.int32))
            base_chunks.append(base_image_sim[keep].detach().cpu().numpy())
            meta_chunks.append(pair_has_meta[keep].detach().cpu().numpy())

    if candidate_chunks:
        pairs = np.concatenate(candidate_chunks)
        base_image_sim = np.concatenate(base_chunks)
        pair_has_meta = np.concatenate(meta_chunks)
    else:
        pairs = np.empty((0, 2), dtype=np.int32)
        base_image_sim = np.empty((0,), dtype=np.float32)
        pair_has_meta = np.empty((0,), dtype=bool)

    print(f"GPU filtering successful: Removed {total_comparisons - len(pairs)} pairs.")
    return pairs, base_image_sim, pair_has_meta


def ssim_batch_gpu(gray_images, pairs):
    """
    Calculate SSIM for candidate pairs on CUDA in batches.

    This uses the standard SSIM formula with a 7x7 average window, matching the
    default skimage window size closely enough for duplicate filtering while
    allowing the expensive part to run as batched tensor work.
    """
    if len(pairs) == 0:
        return np.empty((0,), dtype=np.float32)

    device = torch.device("cuda")
    images = torch.as_tensor(gray_images, device=device).unsqueeze(1)
    pair_tensor = torch.as_tensor(pairs, device=device, dtype=torch.long)
    scores = []
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2

    for start in tqdm(range(0, len(pairs), SSIM_BATCH_SIZE)):
        batch_pairs = pair_tensor[start:start + SSIM_BATCH_SIZE]
        x = images[batch_pairs[:, 0]]
        y = images[batch_pairs[:, 1]]

        mu_x = F.avg_pool2d(x, kernel_size=7, stride=1)
        mu_y = F.avg_pool2d(y, kernel_size=7, stride=1)
        mu_x_sq = mu_x * mu_x
        mu_y_sq = mu_y * mu_y
        mu_xy = mu_x * mu_y

        sigma_x_sq = F.avg_pool2d(x * x, kernel_size=7, stride=1) - mu_x_sq
        sigma_y_sq = F.avg_pool2d(y * y, kernel_size=7, stride=1) - mu_y_sq
        sigma_xy = F.avg_pool2d(x * y, kernel_size=7, stride=1) - mu_xy

        numerator = (2.0 * mu_xy + c1) * (2.0 * sigma_xy + c2)
        denominator = (mu_x_sq + mu_y_sq + c1) * (sigma_x_sq + sigma_y_sq + c2)
        batch_scores = (numerator / denominator).mean(dim=(1, 2, 3)).clamp(0.0, 1.0)
        scores.append(batch_scores.detach().cpu().numpy())

    return np.concatenate(scores).astype(np.float32)


def ssim_batch_cpu(gray_images, pairs, valid_images):
    """Calculate SSIM for candidate pairs on CPU using skimage."""
    scores = np.zeros((len(pairs),), dtype=np.float32)
    for idx, (i, j) in enumerate(pairs):
        try:
            scores[idx] = max(0.0, min(1.0, ssim(gray_images[i], gray_images[j], data_range=255)))
        except Exception as e:
            print(f"Warning: Could not calculate SSIM between {valid_images[i]} and {valid_images[j]}: {e}")
            scores[idx] = 0.0
    return scores


def compare_candidates(valid_images, image_data, pairs, base_image_sim, pair_has_meta,
                       gray_images, processing_device, threshold, img_weight, meta_weight):
    """Run SSIM and metadata checks for candidate pairs, then union duplicates."""
    uf = UnionFind(valid_images)
    if len(pairs) == 0:
        return uf

    print(f"Running SSIM and metadata comparisons for {len(pairs)} candidate pairs...")
    print(f"Run mode: {processing_device} ")
    if processing_device == "gpu":
        try:
            ssim_scores = ssim_batch_gpu(gray_images, pairs)
        except Exception as e:
            print(f"Warning: GPU SSIM failed ({e}). Falling back to CPU SSIM.")
            ssim_scores = ssim_batch_cpu(gray_images, pairs, valid_images)
    else:
        ssim_scores = ssim_batch_cpu(gray_images, pairs, valid_images)

    image_scores = base_image_sim + (0.30 * ssim_scores)
    pair_has_meta = np.asarray(pair_has_meta, dtype=bool)

    no_meta_pass = np.where((~pair_has_meta) & (image_scores >= threshold))[0]
    for k in tqdm(no_meta_pass, desc="union no-metadata pairs", total=len(no_meta_pass)):
        i, j = pairs[k]
        uf.union(valid_images[i], valid_images[j])

    weighted_image_scores = img_weight * image_scores
    meta_direct_pass = np.where(pair_has_meta & (weighted_image_scores >= threshold))[0]
    for k in tqdm(meta_direct_pass, desc="union image-pass metadata pairs", total=len(meta_direct_pass)):
        i, j = pairs[k]
        uf.union(valid_images[i], valid_images[j])

    if meta_weight <= 0:
        print("Metadata weight is 0. Skipping metadata text comparisons.")
        return uf

    # Only these pairs still need SequenceMatcher:
    # - both images have metadata
    # - image score alone does not already pass
    # - even perfect metadata could still push the final score over threshold
    meta_possible_pass = weighted_image_scores + meta_weight
    meta_compare_indices = np.where(
        pair_has_meta
        & (weighted_image_scores < threshold)
        & (meta_possible_pass >= threshold)
    )[0]

    skipped_meta = int(np.count_nonzero(pair_has_meta) - len(meta_direct_pass) - len(meta_compare_indices))
    if skipped_meta > 0:
        print(f"Skipped {skipped_meta} metadata comparisons that cannot reach the threshold.")

    lowered_metadata = [
        image_data[img][1].lower() if image_data[img][1] is not None else None
        for img in valid_images
    ]
    metadata_cache = {}
    for k in tqdm(meta_compare_indices, desc="metadata pairs", total=len(meta_compare_indices)):
        i, j = pairs[k]
        img1 = valid_images[i]
        img2 = valid_images[j]
        text1 = lowered_metadata[i]
        text2 = lowered_metadata[j]
        required_metadata_sim = (threshold - weighted_image_scores[k]) / meta_weight

        if text1 == text2:
            metadata_sim = 1.0
        else:
            cache_key = (text1, text2) if text1 <= text2 else (text2, text1)
            metadata_sim = metadata_cache.get(cache_key)
            if metadata_sim is None:
                matcher = SequenceMatcher(None, text1, text2)
                if matcher.quick_ratio() < required_metadata_sim:
                    metadata_sim = 0.0
                else:
                    metadata_sim = matcher.ratio()
                metadata_cache[cache_key] = metadata_sim

        final_score = weighted_image_scores[k] + (meta_weight * metadata_sim)
        if final_score >= threshold:
            uf.union(img1, img2)

    return uf


def move_duplicate_groups(folder_path, duplicate_groups):
    """Move duplicate files into duplicate_groups/Group_N folders."""
    groups_dir = os.path.join(folder_path, "duplicate_groups")
    os.makedirs(groups_dir, exist_ok=True)
    print(f"\nMoving duplicate files into group folders inside: {groups_dir}...")

    for group_idx, paths in enumerate(duplicate_groups.values(), start=1):
        group_dir = os.path.join(groups_dir, f"Group_{group_idx}")
        os.makedirs(group_dir, exist_ok=True)
        for path in paths:
            try:
                filename = os.path.basename(path)
                dest_path = os.path.join(group_dir, filename)

                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(filename)
                    counter = 1
                    while True:
                        new_filename = f"{base}_{counter}{ext}"
                        dest_path = os.path.join(group_dir, new_filename)
                        if not os.path.exists(dest_path):
                            break
                        counter += 1

                shutil.move(path, dest_path)
                print(f"  Moved: {path} -> {dest_path}")
            except Exception as e:
                print(f"  Error moving {path}: {e}")

    print("\nAll duplicate files have been organized successfully.")


def main():
    print("=== Duplicate Image and Metadata Checker 2 ===")

    while True:
        folder_path = input("Enter the path of the folder to scan: ").strip()
        if not folder_path:
            print("Folder path cannot be empty.")
            continue
        if not os.path.isdir(folder_path):
            print(f"Error: '{folder_path}' is not a valid directory.")
            continue
        break

    threshold_input = input("Enter similarity threshold (0.0 to 1.0, default 0.9): ").strip()
    if threshold_input == "":
        threshold = 0.9
    else:
        try:
            threshold = float(threshold_input)
            if not (0.0 <= threshold <= 1.0):
                raise ValueError
        except ValueError:
            print("Invalid input. Using default threshold of 0.9.")
            threshold = 0.9

    img_weight_input = input("Enter weight for image similarity (0.0 to 1.0, default 0.1): ").strip()
    if img_weight_input == "":
        img_weight = 0.1
    else:
        try:
            img_weight = float(img_weight_input)
            if not (0.0 <= img_weight <= 1.0):
                raise ValueError
        except ValueError:
            print("Invalid input. Using default image weight of 0.1.")
            img_weight = 0.1

    meta_weight = 1.0 - img_weight
    print(f"Metadata similarity weight set to: {meta_weight:.2f}")
    processing_device = choose_processing_device()

    print("\nScanning directory and computing image features...")
    image_files = scan_directory(folder_path)
    if not image_files:
        print("No image files found in the specified directory.")
        return

    print(f"Found {len(image_files)} image files. Processing...")
    if len(image_files) > 500:
        print("Large folder detected (>500 images). Candidate filtering and batched SSIM will be used.")

    image_data = {}
    valid_images = []
    for idx, img_path in enumerate(image_files, start=1):
        features = get_image_features(img_path)
        if features is not None:
            meta_content = extract_image_metadata(img_path)
            image_data[img_path] = (features, meta_content)
            valid_images.append(img_path)
        if idx % 100 == 0:
            print(f"  Processed {idx}/{len(image_files)} files...")

    print(f"Successfully processed and analyzed {len(valid_images)} images.")
    n = len(valid_images)
    total_comparisons = (n * (n - 1)) // 2
    print(f"Comparing {total_comparisons} pairs of files...")

    if total_comparisons > 0:
        matrices = build_feature_matrices(valid_images, image_data)
        p_hashes, d_hashes, colors, brightness, gray_images, has_metadata = matrices

        if processing_device == "gpu":
            try:
                pairs, base_image_sim, pair_has_meta = filter_pairs_gpu(
                    p_hashes, d_hashes, colors, brightness, has_metadata, threshold, img_weight, meta_weight
                )
            except Exception as e:
                print(f"Warning: GPU pair filtering failed ({e}). Falling back to CPU filtering.")
                processing_device = "cpu"
                pairs, base_image_sim, pair_has_meta = filter_pairs_cpu(
                    p_hashes, d_hashes, colors, brightness, has_metadata, threshold, img_weight, meta_weight
                )
        else:
            pairs, base_image_sim, pair_has_meta = filter_pairs_cpu(
                p_hashes, d_hashes, colors, brightness, has_metadata, threshold, img_weight, meta_weight
            )

        uf = compare_candidates(
            valid_images,
            image_data,
            pairs,
            base_image_sim,
            pair_has_meta,
            gray_images,
            processing_device,
            threshold,
            img_weight,
            meta_weight,
        )
    else:
        uf = UnionFind(valid_images)

    groups = defaultdict(list)
    for img in valid_images:
        groups[uf.find(img)].append(img)

    duplicate_groups = {root: paths for root, paths in groups.items() if len(paths) > 1}

    print("\n" + "=" * 50)
    print("RESULTS:")
    print("=" * 50)

    if not duplicate_groups:
        print("No duplicate files found.")
        print(f"Folder scanned: {os.path.abspath(folder_path)}")
        print("Number of duplicate files in the folder: 0")
        return

    print("List of duplicate files in the folder:")
    total_duplicate_files = 0
    for group_idx, paths in enumerate(duplicate_groups.values(), start=1):
        print(f"\nGroup {group_idx}:")
        for path in paths:
            _, meta_content = image_data[path]
            meta_str = " (Has Embedded Metadata)" if meta_content else " (No Metadata)"
            print(f"  - {path}{meta_str}")
        total_duplicate_files += len(paths)

    print("\n" + "-" * 50)
    print(f"Path of folder containing duplicate files: {os.path.abspath(folder_path)}")
    print(f"Number of duplicate groups found: {len(duplicate_groups)}")
    print(f"Total duplicate files (including original copies): {total_duplicate_files}")
    print(f"Number of redundant files (copies that can be deleted): {total_duplicate_files - len(duplicate_groups)}")
    print("=" * 50)

    move_duplicate_groups(folder_path, duplicate_groups)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(1)

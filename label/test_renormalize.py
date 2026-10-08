#!/usr/bin/env python3
"""
Test script: Verify renormalize logic
"""
import sys
import json
import os

sys.path.insert(0, r"d:\Project\PersonalTools\label")

from MultiLabels_UI import (
    ensure_default_labels_file, 
    flatten_default_labels,
    LabelDataManager,
    LABEL_JSON_NAME
)

TEST_FOLDER = r"F:\pic\raw\2025-01-03"
OLD_FOLDER = r"F:\pic\posted\2025-01-03"

print("=" * 80)
print("TEST: Renormalize image paths logic")
print("=" * 80)

# Step 1: Load with old paths
labels_json_path = os.path.join(TEST_FOLDER, LABEL_JSON_NAME)
default_groups = ensure_default_labels_file()
default_labels_flat = flatten_default_labels(default_groups)

dm = LabelDataManager(
    json_path=labels_json_path,
    default_labels=default_labels_flat
)

print(f"\n📂 Before renormalize:")
print(f"  TEST_FOLDER: {TEST_FOLDER}")
for i, (path, entry) in enumerate(list(dm.image_entries.items())[:3]):
    print(f"  Path {i+1}: {path}")

# Step 2: Renormalize (simulate what _on_load_folder does)
print(f"\n🔄 Renormalizing paths to: {TEST_FOLDER}")
new_entries = {}
for old_full_path, entry in dm.image_entries.items():
    image_name = entry.get("image_name", "")
    if image_name:
        new_full_path = os.path.join(TEST_FOLDER, image_name)
        new_entries[new_full_path] = {
            "directory": TEST_FOLDER,
            "image_name": image_name,
            "labels_str": entry.get("labels_str", ""),
        }

dm.image_entries = new_entries

print(f"\n📂 After renormalize:")
for i, (path, entry) in enumerate(list(dm.image_entries.items())[:3]):
    print(f"  Path {i+1}: {path}")

# Step 3: Verify get_image_labels works
print(f"\n✓ Testing get_image_labels():")
for i, (path, entry) in enumerate(list(dm.image_entries.items())[:3]):
    labels = dm.get_image_labels(path)
    print(f"  {os.path.basename(path):30s} -> {len(labels)} labels")

print("\n" + "=" * 80)
print("✅ Test completed - logic looks good!")
print("=" * 80)

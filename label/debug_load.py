#!/usr/bin/env python3
"""
Debug script: Kiểm tra tại sao labels không được load
"""
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, r"d:\Project\PersonalTools\label")

from MultiLabels_UI import (
    ensure_default_labels_file, 
    flatten_default_labels,
    merge_labels_with_defaults,
    LabelDataManager,
    DEFAULT_LABELS_PATH,
    LABEL_JSON_NAME
)

TEST_FOLDER = r"F:\pic\raw\2025-01-03"

print("=" * 80)
print("DEBUG: Why labels.json is not loading correctly")
print("=" * 80)

# Step 1: Check labels.json content
labels_json_path = os.path.join(TEST_FOLDER, LABEL_JSON_NAME)
print(f"\n📂 Reading labels.json from: {labels_json_path}")

with open(labels_json_path, 'r', encoding='utf-8') as f:
    old_data = json.load(f)

print(f"\n✓ Keys in labels.json: {list(old_data.keys())}")
print(f"✓ Number of label_names: {len(old_data.get('label_names', {}))}")
print(f"✓ Number of list_image: {len(old_data.get('list_image', []))}")

# Show first 3 images
print(f"\n📷 First 3 images in labels.json:")
for i, item in enumerate(old_data.get('list_image', [])[:3]):
    print(f"\n  Image {i+1}:")
    print(f"    directory: {item.get('directory')}")
    print(f"    image_name: {item.get('image_name')}")
    print(f"    labels: {item.get('labels')}")

# Step 2: Load with LabelDataManager
print(f"\n" + "=" * 80)
print("Loading with LabelDataManager")
print("=" * 80)

default_groups = ensure_default_labels_file()
default_labels_flat = flatten_default_labels(default_groups)
print(f"\n✓ Default labels: {len(default_labels_flat)} items")

dm = LabelDataManager(
    json_path=labels_json_path,
    default_labels=default_labels_flat
)

print(f"\n✓ Loaded {len(dm.label_names)} label_names")
print(f"✓ Loaded {len(dm.image_entries)} image_entries")

# Show content
print(f"\n📋 First 3 image_entries in memory:")
for i, (full_path, entry) in enumerate(list(dm.image_entries.items())[:3]):
    print(f"\n  Entry {i+1}:")
    print(f"    full_path: {full_path}")
    print(f"    directory: {entry.get('directory')}")
    print(f"    image_name: {entry.get('image_name')}")
    print(f"    labels_str: {entry.get('labels_str')}")

# Step 3: Check if image files exist
print(f"\n" + "=" * 80)
print("Checking if image files exist")
print("=" * 80)

for i, (full_path, entry) in enumerate(list(dm.image_entries.items())[:3]):
    exists = os.path.exists(full_path)
    print(f"  {os.path.basename(full_path):30s} {'✓ exists' if exists else '✗ NOT FOUND'}")

# Step 4: Test get_image_labels
print(f"\n" + "=" * 80)
print("Testing get_image_labels()")
print("=" * 80)

for i, (full_path, entry) in enumerate(list(dm.image_entries.items())[:3]):
    labels = dm.get_image_labels(full_path)
    print(f"\n  Image {i+1}: {os.path.basename(full_path)}")
    print(f"    get_image_labels result: {labels}")
    print(f"    number of labels: {len(labels)}")

print("\n" + "=" * 80)
print("✅ Debug completed")
print("=" * 80)

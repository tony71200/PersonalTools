#!/usr/bin/env python3
"""
Test script: Load folder with labels.json and verify merge logic
"""
import sys
import json
import os
from pathlib import Path

# Add current dir to path
sys.path.insert(0, r"d:\Project\PersonalTools\label")

# Import từ MultiLabels_UI
from MultiLabels_UI import (
    ensure_default_labels_file, 
    flatten_default_labels,
    merge_labels_with_defaults,
    load_label_descriptions,
    LabelDataManager,
    DEFAULT_LABELS_PATH,
    LABEL_JSON_NAME
)

TEST_FOLDER = r"F:\pic\raw\2025-01-03"

print("=" * 80)
print("TEST: Load folder with merge logic")
print("=" * 80)

# Step 1: Load default labels
print("\n📚 Step 1: Load default_labels.json")
default_groups = ensure_default_labels_file()
default_labels_flat = flatten_default_labels(default_groups)
print(f"  ✓ Loaded {len(default_labels_flat)} default labels")
print(f"  Labels: {default_labels_flat[:5]}... (showing first 5)")

# Step 2: Check if test folder has labels.json
labels_json_path = os.path.join(TEST_FOLDER, LABEL_JSON_NAME)
print(f"\n📂 Step 2: Check test folder: {TEST_FOLDER}")
if os.path.exists(labels_json_path):
    print(f"  ✓ labels.json exists at: {labels_json_path}")
    
    # Read existing labels
    with open(labels_json_path, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
    old_label_names = {int(k): v for k, v in old_data.get('label_names', {}).items()}
    
    print(f"\n  Old label_names ({len(old_label_names)} items):")
    for k, v in sorted(old_label_names.items())[:10]:
        print(f"    {k}: {v}")
    if len(old_label_names) > 10:
        print(f"    ... ({len(old_label_names) - 10} more)")
else:
    print(f"  ⚠ labels.json NOT found")
    old_label_names = {}

# Step 3: Test merge logic
print(f"\n🔄 Step 3: Test merge logic")
if old_label_names:
    merged = merge_labels_with_defaults(old_label_names, default_labels_flat)
    print(f"  Merged result ({len(merged)} items):")
    for k, v in sorted(merged.items())[:15]:
        in_default = v in default_labels_flat
        status = "✓ from default" if in_default else "🟡 custom"
        print(f"    {k}: {v:30s} {status}")
    if len(merged) > 15:
        print(f"    ... ({len(merged) - 15} more)")

# Step 4: Load with LabelDataManager
print(f"\n📖 Step 4: Load with LabelDataManager")
dm = LabelDataManager(
    json_path=labels_json_path,
    default_labels=default_labels_flat
)
print(f"  ✓ Loaded {len(dm.label_names)} labels")
print(f"  Label names (first 15):")
for k, v in sorted(dm.label_names.items())[:15]:
    in_default = v in default_labels_flat
    status = "✓ from default" if in_default else "🟡 custom"
    print(f"    {k}: {v:30s} {status}")

# Step 5: Check image labels
print(f"\n🖼️ Step 5: Check image labels")
if dm.image_entries:
    print(f"  ✓ Found {len(dm.image_entries)} images")
    for i, (full_path, entry) in enumerate(list(dm.image_entries.items())[:3]):
        labels_str = entry.get('labels_str', '').strip()
        if labels_str:
            print(f"\n    Image {i+1}: {os.path.basename(full_path)}")
            print(f"      Labels: {labels_str}")
        else:
            print(f"\n    Image {i+1}: {os.path.basename(full_path)} (no labels)")
    if len(dm.image_entries) > 3:
        print(f"\n    ... ({len(dm.image_entries) - 3} more images)")
else:
    print(f"  ⚠ No images found")

print("\n" + "=" * 80)
print("✅ Test completed successfully!")
print("=" * 80)

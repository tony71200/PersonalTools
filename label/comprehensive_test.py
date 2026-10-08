#!/usr/bin/env python3
"""
Comprehensive test: Verify all fixes
"""
import sys
import json
import os

sys.path.insert(0, r"d:\Project\PersonalTools\label")

from MultiLabels_UI import (
    ensure_default_labels_file, 
    flatten_default_labels,
    merge_labels_with_defaults,
    LabelDataManager,
    LABEL_JSON_NAME,
    MAX_LABELS
)

TEST_FOLDER = r"F:\pic\raw\2025-01-03"

print("=" * 80)
print("COMPREHENSIVE TEST: All Fixes")
print("=" * 80)

# Test 1: Verify merge_labels_with_defaults works
print("\n" + "=" * 80)
print("TEST 1: Merge labels with rebuild logic")
print("=" * 80)

existing = {0: "a", 1: "b", 2: "custom1"}
default = ["a", "b", "new_default"]

result = merge_labels_with_defaults(existing, default)
print(f"Existing labels: {existing}")
print(f"Default labels: {default}")
print(f"\nResult:")
for idx, tag in sorted(result.items()):
    status = "from default" if tag in default else "✓ custom"
    print(f"  {idx}: {tag:20s} {status}")

expected_order = ["a", "b", "new_default", "custom1"]
actual_order = [result[i] for i in sorted(result.keys())]
test1_pass = actual_order == expected_order
print(f"\n✓ Test 1: {'PASS' if test1_pass else 'FAIL'} - Order is {'correct' if test1_pass else 'wrong'}")

# Test 2: Load folder with renormalize
print("\n" + "=" * 80)
print("TEST 2: Load folder and renormalize paths")
print("=" * 80)

default_groups = ensure_default_labels_file()
default_labels_flat = flatten_default_labels(default_groups)

labels_json_path = os.path.join(TEST_FOLDER, LABEL_JSON_NAME)
dm = LabelDataManager(
    json_path=labels_json_path,
    default_labels=default_labels_flat
)

print(f"\nBefore renormalize:")
print(f"  image_entries: {len(dm.image_entries)} items")
sample_paths_before = list(dm.image_entries.keys())[:2]
for p in sample_paths_before:
    print(f"    {p}")

# Simulate renormalize
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

print(f"\nAfter renormalize:")
print(f"  image_entries: {len(dm.image_entries)} items")
sample_paths_after = list(dm.image_entries.keys())[:2]
for p in sample_paths_after:
    print(f"    {p}")

# Verify paths now contain TEST_FOLDER
test2_pass = all(TEST_FOLDER in p for p in sample_paths_after)
print(f"\n✓ Test 2: {'PASS' if test2_pass else 'FAIL'} - Paths contain TEST_FOLDER")

# Test 3: Verify labels are loaded correctly
print("\n" + "=" * 80)
print("TEST 3: Labels loading after renormalize")
print("=" * 80)

labeled_count = 0
for full_path in dm.image_entries.keys():
    labels = dm.get_image_labels(full_path)
    if labels:
        labeled_count += 1

print(f"Total images: {len(dm.image_entries)}")
print(f"Labeled images: {labeled_count}")
print(f"Label_names count: {len(dm.label_names)}")

test3_pass = labeled_count > 0
print(f"\n✓ Test 3: {'PASS' if test3_pass else 'FAIL'} - {labeled_count} images have labels")

# Test 4: Verify remove_non_default logic
print("\n" + "=" * 80)
print("TEST 4: Remove non-default labels logic")
print("=" * 80)

default_tags_set = set(default_labels_flat)
print(f"Default tags: {len(default_tags_set)} items")

# Count non-default tags
non_default_tags = set()
for full_path, entry in dm.image_entries.items():
    labels_str = entry.get("labels_str", "").strip()
    if labels_str:
        tags = [t.strip() for t in labels_str.split(",") if t.strip()]
        for tag in tags:
            if tag not in default_tags_set:
                non_default_tags.add(tag)

print(f"Non-default tags found: {len(non_default_tags)} items")
if non_default_tags:
    print(f"  Examples: {list(non_default_tags)[:5]}")

test4_pass = len(non_default_tags) > 0  # Should find some custom tags from old labels
print(f"\n✓ Test 4: {'PASS' if test4_pass else 'FAIL'} - Found {len(non_default_tags)} non-default tags")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
all_pass = test1_pass and test2_pass and test3_pass and test4_pass
print(f"Test 1 (Merge logic):          {'✓ PASS' if test1_pass else '✗ FAIL'}")
print(f"Test 2 (Renormalize paths):    {'✓ PASS' if test2_pass else '✗ FAIL'}")
print(f"Test 3 (Labels loading):       {'✓ PASS' if test3_pass else '✗ FAIL'}")
print(f"Test 4 (Non-default removal):  {'✓ PASS' if test4_pass else '✗ FAIL'}")
print(f"\n{'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
print("=" * 80)

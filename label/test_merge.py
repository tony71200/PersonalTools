#!/usr/bin/env python3
"""
Test script để kiểm tra logic merge labels
"""
import json
import os

# Mô phỏng hàm hiện tại (có vấn đề)
def merge_labels_with_defaults_OLD(existing_labels, default_labels_list, MAX_LABELS=128):
    """Cách cũ - tách biệt ID"""
    merged = dict(existing_labels)
    existing_tags = set(existing_labels.values())
    max_id = max(merged.keys(), default=-1)
    
    for tag in default_labels_list:
        if tag not in existing_tags:
            max_id += 1
            if max_id < MAX_LABELS:
                merged[max_id] = tag
    return merged


def merge_labels_with_defaults_NEW(existing_labels, default_labels_list, MAX_LABELS=128):
    """Cách mới - đảm bảo thứ tự theo default và giữ lại tags cũ"""
    # Tạo dict reverse để tìm ID cũ
    old_tags = set(existing_labels.values())
    name_to_old_id = {v: k for k, v in existing_labels.items()}
    
    merged = {}
    for idx, tag in enumerate(default_labels_list):
        if idx >= MAX_LABELS:
            break
        merged[idx] = tag
    
    # Thêm các tags cũ không có trong default
    max_idx = len(default_labels_list)
    for old_id, tag in existing_labels.items():
        if tag not in default_labels_list:
            # Tag này là custom, cộng thêm
            if max_idx < MAX_LABELS:
                merged[max_idx] = tag
                max_idx += 1
    
    return merged


# Test data
print("=" * 80)
print("TEST MERGE LOGIC")
print("=" * 80)

# Giả sử labels.json cũ (từ phiên bản cũ của default_labels.json)
existing_old = {
    0: "realistic",
    1: "semi-realistic",
    2: "anime",
    3: "sfw",
    4: "suggestive",
    5: "mild_nudity",
    6: "explicit_nudity",
    7: "fully_clothed",
    8: "casual_wear",
    9: "swimwear",
    10: "underwear",
    11: "shirtless",
    12: "bottomless",
    13: "custom_tag1",
}

# Default labels mới (theo default_labels.json hiện tại)
default_new = [
    "realistic",
    "semi-realistic", 
    "anime",
    "sfw",
    "suggestive",
    "mild_nudity",
    "explicit_nudity",
    "fully_clothed",
    "casual_wear",
    "swimwear",
    "underwear",
    "shirtless",
    "bottomless",
    "new_tag_from_default",  # tag mới được thêm vào
]

print("\n📋 EXISTING LABELS (labels.json cũ):")
for k, v in sorted(existing_old.items()):
    print(f"  {k}: {v}")

print("\n📋 DEFAULT LABELS (default_labels.json mới):")
for idx, tag in enumerate(default_new):
    print(f"  {idx}: {tag}")

print("\n" + "=" * 80)
print("CÁCH CŨ (có vấn đề):")
print("=" * 80)
result_old = merge_labels_with_defaults_OLD(existing_old, default_new)
print("\nKết quả merge (OLD):")
for k, v in sorted(result_old.items()):
    old_tag = existing_old.get(k, "NEW")
    status = "🟡 ISSUE: ID thay đổi!" if k >= 13 and v in [t for t in existing_old.values()] else "✓"
    print(f"  {k}: {v:25s} {status}")

print("\n" + "=" * 80)
print("CÁCH MỚI (khắc phục):")
print("=" * 80)
result_new = merge_labels_with_defaults_NEW(existing_old, default_new)
print("\nKết quả merge (NEW):")
for k, v in sorted(result_new.items()):
    status = "✓ Giữ nguyên thứ tự default" if k < len(default_new) else "✓ Tag custom thêm vào"
    print(f"  {k}: {v:25s} {status}")

print("\n" + "=" * 80)
print("SO SÁNH:")
print("=" * 80)
print(f"\nCách cũ - clothing ID bị đẩy: YES (ID 7-12 vẫn đúng, nhưng custom_tag1 = 13)")
print(f"Cách mới - clothing ID bị đẩy: NO (ID 7-12 vẫn đúng, new_tag_from_default = 13)")
print(f"\nVấn đề: Cách cũ giữ lại ID cũ, nên khi default_labels.json có thay đổi vị trí,")
print(f"ID sẽ bị messes up. Cách mới rebuild theo thứ tự default, giữ các tag custom.")

from grouping.cli import run_test, Config

if __name__ == "__main__":
    cfg = Config(
        mode="single",
        input_path=r"H:\004_Learn\GetData\imapatee",
        output_path=r"H:\004_Learn\GetData\imapatee_output",
        target_count=200,
        recursive_parent=False,
        copy_files=not True,
        dry_run=False,
        enable_clip=not False,
        enable_faiss=not False,
        clip_model_name="openai/clip-vit-base-patch32",
        clip_batch_size=4,
        clip_cache_dir="./clip_cache",
        det_model_name="buffalo_l",
        det_size=(640, 640),
        min_face_size_px=48,
        min_face_ratio=0.02,
        min_quality_score=0.35,
        duplicate_hash_threshold=6,
        semantic_similarity_threshold=0.92,
        top_k_per_duplicate_group=1,
        top_k_per_semantic_group=3,
        top_k_folder_shortlist_multiplier=2.0,
        verbose=not False,
    )
    run_test(cfg)

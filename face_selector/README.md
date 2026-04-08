# Face Selector Project

Chọn ảnh mặt người chất lượng tốt từ một folder hoặc nhiều folder con.

## Features
- `single` mode: chọn từ 1 folder
- `parent` mode: chọn từ nhiều folder con
- InsightFace để detect mặt người
- CLIP optional để semantic grouping
- FAISS optional để tăng tốc semantic grouping
- dHash để near-duplicate grouping
- CSV + JSON report

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py --mode single --input "/data/photos" --output "/data/out" --target 100
python main.py --mode parent --input "/data/parent" --output "/data/out" --target 1000
```

## Notes
- Nếu thiếu `faiss` hoặc `CLIP`, chương trình sẽ fallback an toàn.
- Nếu muốn GPU cho InsightFace, cài `onnxruntime-gpu`.

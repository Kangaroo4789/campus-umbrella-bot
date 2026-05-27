"""
把 labelme 標注的 JSON 檔轉成 YOLO 格式的 .txt 檔。
標注完成後執行：python labelme_to_yolo.py
"""

import json
from pathlib import Path

TRAIN_DIR = Path("train")
LABELS    = ["umbrella"]   # 跟標注時用的名稱一致


def convert_json(json_path: Path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    img_w = data["imageWidth"]
    img_h = data["imageHeight"]
    lines = []

    for shape in data["shapes"]:
        label = shape["label"]
        if label not in LABELS:
            continue
        cls_id = LABELS.index(label)
        pts    = shape["points"]

        # rectangle: [[x1,y1],[x2,y2]]
        # polygon:   多個點，取 bounding box
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)

        cx = ((x1 + x2) / 2) / img_w
        cy = ((y1 + y2) / 2) / img_h
        w  = (x2 - x1) / img_w
        h  = (y2 - y1) / img_h

        # 確保數值在 0~1 範圍內
        cx, cy, w, h = (max(0, min(1, v)) for v in (cx, cy, w, h))
        lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

    if lines:
        labels_dir = TRAIN_DIR / "labels"
        labels_dir.mkdir(exist_ok=True)
        out_path = labels_dir / json_path.with_suffix(".txt").name
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return len(lines)
    return 0


def main():
    json_files = list(TRAIN_DIR.glob("*.json"))
    if not json_files:
        print("❌ train/ 資料夾裡沒有 .json 檔，請先用 labelme 完成標注")
        return

    total_boxes = 0
    for jf in sorted(json_files):
        count = convert_json(jf)
        print(f"  {'✅' if count else '⚠️ '} {jf.name} → {count} 個框")
        total_boxes += count

    print(f"\n✅ 轉換完成：{len(json_files)} 張圖，共 {total_boxes} 個框")
    print("下一步：python prepare_dataset.py")


if __name__ == "__main__":
    main()

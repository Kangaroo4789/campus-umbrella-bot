"""
將 train/ 裡已標注的圖片和 label，分割成 YOLO 訓練格式。
標注完成後執行：python prepare_dataset.py
"""

import os
import shutil
import random
from pathlib import Path

TRAIN_DIR   = Path("train")
DATASET_DIR = Path("dataset")
VAL_RATIO   = 0.2  # 20% 作為驗證集
SEED        = 42

def main():
    image_exts = {".jpg", ".jpeg", ".png"}

    # 找出所有有對應 label 的圖片
    images = []
    for f in TRAIN_DIR.iterdir():
        if f.suffix.lower() in image_exts:
            label = TRAIN_DIR / "labels" / f.with_suffix(".txt").name
            if label.exists():
                images.append(f)
            else:
                print(f"[跳過] 沒有對應 label：{f.name}")

    if not images:
        print("❌ 沒有找到已標注的圖片，請先用 LabelImg 完成標注")
        return

    random.seed(SEED)
    random.shuffle(images)
    val_count = max(1, int(len(images) * VAL_RATIO))
    val_set   = images[:val_count]
    train_set = images[val_count:]

    print(f"✅ 共 {len(images)} 張已標注")
    print(f"   訓練集：{len(train_set)} 張")
    print(f"   驗證集：{len(val_set)} 張")

    for split, items in [("train", train_set), ("val", val_set)]:
        img_dir = DATASET_DIR / "images" / split
        lbl_dir = DATASET_DIR / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_path in items:
            lbl_path = TRAIN_DIR / "labels" / img_path.with_suffix(".txt").name
            shutil.copy2(img_path,  img_dir / img_path.name)
            shutil.copy2(lbl_path,  lbl_dir / img_path.with_suffix(".txt").name)

    # 產生 data.yaml
    yaml_content = f"""\
path: {DATASET_DIR.resolve().as_posix()}
train: images/train
val:   images/val

nc: 1
names: ['umbrella']
"""
    (DATASET_DIR / "data.yaml").write_text(yaml_content, encoding="utf-8")
    print(f"\n✅ dataset/ 資料集已建立")
    print(f"   data.yaml 路徑：{(DATASET_DIR / 'data.yaml').resolve()}")
    print(f"\n下一步：python train_model.py")

if __name__ == "__main__":
    main()

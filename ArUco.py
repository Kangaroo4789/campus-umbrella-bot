import cv2
import numpy as np

# 1. 指定跟我們 app.py 一模一樣的 4x4_50 字典
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

# 2. 生成 ID 為 7 的雨傘貼紙（大小設為 200x200 像素）
# cv2.aruco.generateImageMarker(字典, ID, 像素大小)
marker_image = cv2.aruco.generateImageMarker(aruco_dict, 7, 200)

# 3. 儲存成圖片
cv2.imwrite("umbrella_marker_007.png", marker_image)
print("傘號 007 的 ArUco 碼已生成成功！")
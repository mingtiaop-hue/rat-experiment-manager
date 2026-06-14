# 🐀 动物实验记录与数据管理系统

糖尿病大鼠感染创面愈合实验 — 每鼠4伤口 | 拍照上传 | GraphPad一键导出

## 快速开始

```bash
pip install streamlit pandas openpyxl Pillow qrcode[pil]
streamlit run app.py
```

浏览器打开 `http://localhost:8501`

## 实验设计

- **不电刺激鼠** (8只): 7,9,10,11,13,15,16,17
  - W1→Control / W2→Alginate / W3,W4→Alginate_HJ
- **电刺激鼠** (9只): 1,2,3,4,5,6,8,12,14
  - W1,W2→Pure_ES / W3,W4→Stretched_HJ_ES

每鼠4个伤口，共68个伤口。伤口面积可用ImageJ后补计算。

## 功能

| 模块 | 说明 |
|------|------|
| 📋 日常录入 | 选天→选鼠→填伤口面积→拖拽上传照片 |
| 📦 批量上传 | 一键拖入4张照片，按W1-W4自动分配 |
| 🖼️ 照片长廊 | 单伤口Day1-14全时间线查看 |
| 🔬 跨鼠对比 | 同伤口位多鼠多天横向对比 |
| 📊 数据导出 | Excel含GraphPad Prism格式 |
| 🧪 样本管理 | 取材日组织样本跟踪 |

## 手机端

PC启动后侧边栏显示二维码，手机扫码即可拍照上传。照片自动压缩（1920px, JPEG 85%）。


# OCR Demo

一个基于 **FastAPI** + **PaddleOCR** 的轻量级 OCR（文字识别）服务，并配套 **Edge/Chrome 插件**，支持快捷截图并上传至本地服务进行文字识别。

## 功能特性

* 🎯 **本地 OCR 引擎**：基于 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)，支持中、英和中英混合识别 
* ⚡ **轻量图像预处理**：自动增强小符号和弱对比度文本，提升识别率
* 🌐 **HTTP API 接口**：提供 `/v1/ocr` 接口，支持文件上传或远程 URL 下载
* 🔧 **可调参数**：支持通过 Query/Body 调整 `char_type`、`box_thresh`、`unclip_ratio`、`drop_score`、`max_text_length`、`preprocess` 等参数
* 🖥️ **浏览器插件**：支持快捷键（默认 `Alt+0`）截图网页内容，并调用本地 OCR 服务识别文字
* 📦 **接口跨域 (CORS)**：默认放开（开发阶段），生产环境可收紧



## 项目结构

```
.
├─ ocr_demo                # 后端服务 (FastAPI)
│  ├─ ocr                  # OCR 引擎封装
│  │  ├─ base.py           # 抽象基类定义
│  │  └─ paddle_impl.py    # PaddleOCR 实现
│  ├─ deps.py              # OCR 引擎依赖与单例
│  └─ main.py              # FastAPI 入口 (OCR API)
│
└─ orc-box-edge            # 浏览器插件 (Edge/Chrome MV3)
   ├─ manifest.json        # 插件清单
   ├─ sw.js                # Service Worker (后台截图)
   ├─ content.js           # 插件前端逻辑 (截图、上传、结果展示)
   └─ icons/               # 插件图标
```

---

## 环境依赖

Python 环境依赖在 `requirements.txt`：

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
numpy==1.26.4
opencv-python-headless==4.10.0.84
paddleocr==2.7.0.3
pydantic==2.8.2
```

安装：

```bash
pip install -r requirements.txt
```

---

## 启动后端服务

```bash
# 开发模式
uvicorn ocr_demo.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后可访问：

* 健康检查接口: [http://localhost:8000/healthz](http://localhost:8000/healthz)
* OCR API: `POST http://localhost:8000/v1/ocr`

### API 示例

#### 文件上传 (multipart form)

```bash
curl -X POST "http://localhost:8000/v1/ocr?lang=ch_en&return_boxes=true" \
  -F "file=@test.png"
```

#### JSON 参数 (远程图片)

```json
POST http://localhost:8000/v1/ocr
{
  "file_url": "https://example.com/demo.png",
  "lang": "en",
  "return_boxes": true,
  "char_type": "en_sensitive",
  "box_thresh": 0.45,
  "unclip_ratio": 1.9,
  "drop_score": 0.3,
  "max_text_length": 128,
  "preprocess": 1
}
```

返回示例：

```json
{
  "text": "识别的文字内容",
  "boxes": [
    {
      "text": "某个词",
      "bbox": [100, 50, 200, 80],
      "confidence": 0.97
    }
  ]
}
```

---

## 浏览器插件使用

1. 打开 **Edge/Chrome → 扩展管理 → 加载已解压的扩展**
2. 选择项目中的 `orc-box-edge/` 文件夹
3. 启动后，默认快捷键 **Alt+0** 开始截图
4. 框选区域后，插件会自动调用 `http://localhost:8000/v1/ocr` API，并弹窗显示识别结果

---

## 可配置项

* **后端引擎**：通过环境变量切换

  * `OCR_ENGINE=paddle`（默认）
  * `OCR_LANG=ch`（默认中文，可选 `en`, `ch_en`）

* **插件端点**：`content.js` 中的 `API_BASE`（默认 `http://localhost:8000`） 

---

## 后续扩展

* 🔄 增加异步任务队列（如 Celery/RQ），支持批量/后台 OCR
* ☁️ 接入云端 OCR 服务，提供多引擎选择
* 📝 增强插件 UI，支持复制/导出结果

---

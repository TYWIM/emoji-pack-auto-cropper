# 表情切切

把包含多个表情的 PNG 拼图识别并裁成独立的 1:1 图片，一次导出：

- `PNG_300x300/`：300×300 PNG
- `GIF_300x300/`：同名、同尺寸 GIF
- 大文件夹根目录：第一张表情额外生成的 200×200 PNG

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

浏览器打开 `http://127.0.0.1:8000`。

## 测试

```powershell
python -m unittest discover -s tests -v
```

前端 UI 冒烟测试（需先启动服务）：

```powershell
npm install playwright --no-save
node tests/ui_smoke.js
```

详细设计、约束和验收标准见 [开发文档](docs/DEVELOPMENT.md)。

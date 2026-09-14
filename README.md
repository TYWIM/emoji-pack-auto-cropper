# 表情包自动裁切工具

一个本地运行的表情包拼图处理工具。上传包含多个表情的 PNG 图片后，可以自动识别表情区域、手动修正裁剪框，并一次导出整理好的 PNG、GIF 和首图。

> 暂用产品名：表情切切。项目名称后续可以直接调整，不影响现有功能。

## 功能

- 自动识别一张拼图中的多个表情
- 按表情实际边界生成 1:1 裁剪框
- 支持原图缩放、滚动查看和完整显示
- 支持移动、缩放、新增、删除裁剪框
- 支持停用误识别结果和批量命名
- 输出 300×300 PNG 与同名 GIF
- 第一张表情额外生成 200×200 PNG
- 按约定目录结构打包下载 ZIP
- 所有图片处理均在本机服务中完成，不上传到第三方平台

## 技术栈

- FastAPI：本地 HTTP 服务和导出接口
- OpenCV + NumPy：前景、轮廓和表情候选识别
- Pillow：裁剪、缩放、PNG/GIF 编码
- 原生 HTML、CSS、JavaScript：交互式裁剪工作台

## 本地运行

需要 Python 3.11 或更高版本。

```powershell
git clone https://github.com/TYWIM/emoji-pack-auto-cropper.git
cd emoji-pack-auto-cropper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

## 使用流程

1. 上传包含多个表情的 PNG 拼图。
2. 检查自动识别结果；规则排列的拼图也可切换到规则网格模式。
3. 使用“手动修正”移动、缩放、新增或删除裁剪框。
4. 填写每张表情的名称，取消不需要的结果。
5. 点击“下载文件夹”，获取 ZIP 文件。

导出目录示例：

```text
我的表情包/
├── PNG_300x300/
│   ├── 开心_01.png
│   └── 疑问_02.png
├── GIF_300x300/
│   ├── 开心_01.gif
│   └── 疑问_02.gif
└── 开心_01_200.png
```

## 测试

后端和图像处理测试：

```powershell
python -m unittest discover -s tests -v
```

前端 UI 冒烟测试（需先启动服务）：

```powershell
npm install playwright --no-save
node tests/ui_smoke.js
```

## 当前限制

- 目前仅支持 PNG 输入。
- GIF 输出为单帧格式转换，不会从静态图片生成动画。
- 自动识别采用传统图像算法；复杂拼图可能需要使用规则网格或手动修正。
- 临时处理记录保存在内存中，服务重启后需要重新上传图片。

详细设计和验收规则见 [开发文档](docs/DEVELOPMENT.md)。

## 贡献

欢迎提交 Issue 和 Pull Request。提交修改前请运行测试，并尽量为图像识别边界情况补充回归样例。

## 许可证

本项目采用 [MIT License](LICENSE)。

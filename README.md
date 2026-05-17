# 抖音二次元图集发布工具

本项目是一个本地运行的抖音创作者服务平台半自动发布工具。它可以导入本地图片、视频和音频素材，按图集或视频任务生成文案，并通过浏览器自动化把素材和文案填入抖音创作者服务平台，最终停在发布前确认页。

## 当前能力

- 本地 Web 工作台
- 本地图片、视频、音频素材导入和扫描
- 默认 4 张图片一组
- 图集发布任务
- 本地视频发布任务
- 多图自动混剪成 9:16 短视频
- 混剪视频支持轻动效、淡入淡出和背景音乐
- 图集发布前可选自动转成 9:16
- DeepSeek 文案生成
- 未配置 DeepSeek Key 时使用本地模板
- SQLite 保存任务和发布记录
- Playwright 半自动打开抖音创作者服务平台并尝试上传、填文案
- 任务支持编辑、确认发布结果、删除草稿任务

## 推荐环境

优先建议使用 `conda`，因为当前机器上的 MSYS2 Python 对 `playwright` 包兼容性较差。

### conda 创建环境

```powershell
conda env create -f environment.yml
conda activate douyin-publisher
python -m playwright install chromium
```

如果你已经有自己的 conda 环境，也可以直接：

```powershell
conda create -n douyin-publisher python=3.12 pip -y
conda activate douyin-publisher
pip install -r requirements.txt
python -m playwright install chromium
```

## 启动

激活 `conda` 环境后：

```powershell
python -m app.main
```

或者直接：

```powershell
.\start.ps1
```

打开：

```text
http://127.0.0.1:8765
```

## .env 配置

项目已支持直接读取根目录 `.env`，不需要额外安装 `python-dotenv`。

先复制模板：

```powershell
Copy-Item .env.example .env
```

常用配置：

```env
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DOUYIN_CREATOR_UPLOAD_URL=https://creator.douyin.com/creator-micro/content/upload
BROWSER_PATH=
BROWSER_PROFILE_DIR=D:\Desktop\Job\Tiktok-picture\data\browser-profile
UPLOAD_SELECTOR=input[type='file']
TITLE_SELECTOR=
CAPTION_SELECTOR=
```

说明：

- 页面里保存的配置会写入 `data/config.json`
- `.env` 适合放默认值和敏感配置
- 环境变量优先级高于页面默认配置

## 安装自动发布依赖

如果你不使用 conda，也可以用标准 Windows Python 虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

如果使用的是 MSYS2 Python，可能无法安装 Playwright。遇到 `No matching distribution found for playwright` 时，请改用 `conda` 或 python.org 安装的 Windows Python。

当前项目的本地工作台、素材扫描、文案生成和任务记录不依赖 Playwright；只有点击“半自动发布”时需要 Playwright。

## 使用流程

1. 启动本地服务。
2. 在工作台配置 DeepSeek API Key。
3. 在“素材”区选择文件夹或文件，系统会复制到本地工作目录。
4. 选择发布类型：图集、直接发布本地视频，或用图片混剪成视频。
5. 如果需要混剪视频，可以选择转场效果、背景音乐、音乐起始秒数和片段时长。
6. 点击“创建任务”，系统会生成标题、正文和话题。
7. 检查并编辑任务里的标题、正文和话题。
8. 点击任务行里的“半自动发布”。
9. 浏览器打开抖音创作者服务平台后，检查内容并手动点击发布。
10. 发布完成后，在任务行点击“确认”记录结果，或删除不需要的草稿任务。

## 注意

- 首版不会自动点击最终发布按钮。
- 系统不会处理验证码、短信验证、人脸验证或账号风控。
- 抖音页面结构变化时，可能需要在配置里调整上传控件、标题和文案选择器。
- 页面会把选择的素材复制到 `data/uploads/`，混剪视频输出到 `data/outputs/`。
- 图片混剪视频依赖 FFmpeg；使用 `environment.yml` 创建 conda 环境时会自动安装。
- `start.ps1` 会优先使用当前激活的 `conda` 环境；如果没有，再尝试项目内 `.venv`。

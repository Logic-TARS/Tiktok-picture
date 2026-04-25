# 抖音二次元图集发布工具

本项目是一个本地运行的抖音创作者服务平台半自动发布工具。首版固定面向多图图集场景：扫描本地图片，按 4 张一组创建任务，使用 DeepSeek 生成文案，并通过浏览器自动化把素材和文案填入抖音创作者服务平台，最终停在发布前确认页。

## 当前能力

- 本地 Web 工作台
- 本地图片路径扫描
- 默认 4 张图片一组
- DeepSeek 文案生成
- 未配置 DeepSeek Key 时使用本地模板
- SQLite 保存任务和发布记录
- Playwright 半自动打开抖音创作者服务平台并尝试上传、填文案

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
3. 输入本地图片文件夹路径。
4. 点击“扫描素材”。
5. 点击“创建4图任务”。
6. 检查并编辑生成的标题、正文和话题。
7. 点击任务行里的“半自动发布”。
8. 浏览器打开抖音创作者服务平台后，检查内容并手动点击发布。

## 注意

- 首版不会自动点击最终发布按钮。
- 系统不会处理验证码、短信验证、人脸验证或账号风控。
- 抖音页面结构变化时，可能需要在配置里调整上传控件、标题和文案选择器。
- 普通浏览器文件上传控件无法提供本地绝对路径，所以本工具使用“输入本地路径并由后端扫描”的方式读取素材。
- `start.ps1` 会优先使用当前激活的 `conda` 环境；如果没有，再尝试项目内 `.venv`。

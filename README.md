# SnoAkari gpt-image WebUI

[![Version](https://img.shields.io/badge/version-2.0.0-green)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)

零依赖的本地 WebUI：在浏览器里调用任意 NewAPI 中转站的 gpt-image / nano-banana / gemini 等图像模型，支持文生图、改图、多图融合。纯 Python 标准库实现，无需安装任何第三方库，Windows 双击即用，支持跨平台运行。

> 密钥只保存在本机 `data/config.json`，请求由本地服务端代理转发，不经任何第三方服务器。

## 目录

- [快速开始](#快速开始)
- [功能](#功能)
- [配置](#配置)
- [参数速查](#参数速查)
- [中转站实测行为](#中转站实测行为)
- [项目结构](#项目结构)
- [从 v1 升级](#从-v1-升级)
- [常见问题](#常见问题)
- [更新日志](#更新日志)
- [License](#license)

## 快速开始

### 前置要求

- Python 3.8+（无需 pip 安装任何包）

### 安装与启动

```bash
git clone https://github.com/Licne/snoakari-gpt-image-webui.git
cd snoakari-gpt-image-webui
python app.py
```

Windows 用户直接双击 **`启动WebUI.bat`**，浏览器自动打开 http://127.0.0.1:8787（若未弹出，手动访问）。关闭服务：关掉命令行窗口或 Ctrl+C。

### 首次配置

1. 复制 `config.example.json` 为 `data/config.json`
2. 填入你的中转站地址与 API 密钥：

```json
{ "api_key": "sk-你的密钥", "base_url": "https://你的中转站地址", "model": "gpt-image-1", "proxy": "" }
```

3. 重启服务即可。之后也可在页面右上角 ⚙ 设置里随时修改、管理多组中转站。

## 功能

- **文生图 / 改图·多图融合**：拖拽上传 1~16 张图，支持 PNG 蒙版局部重绘
- **后台任务**：生成中可「转入后台」解放前台继续填参；任务面板实时进度（真并行）、中途中止、失败一键重试（原参数含改图输入图）
- **中转站分组**：每组独立地址/密钥/代理/模型列表，可从接口拉取模型，页顶一键切换
- **模型系列参数适配**：gpt-image 系全参数；nano-banana / gemini / grok 系仅基础参数，不兼容参数自动隐藏不下发
- **收藏 / 重命名 / 引用 / 本地查看**：历史记录保存于 `data/outputs/`，卡片操作直接复用素材
- 隐私遮罩（预览图模糊开关）、参数浏览器本地记忆、出站代理（http/https）、生成按钮防连点
- 文件名自动前缀：`档位_模型_分组_时间戳`，一眼可溯

## 配置

配置文件为 `data/config.json`，也可全部在页面 ⚙ 设置中维护：

| 字段 | 说明 | 默认 |
|---|---|---|
| `api_key` | 中转站 API 密钥（也可用环境变量 `GPT_IMAGE_API_KEY` 覆盖） | 必填 |
| `base_url` | 中转站地址 | 必填 |
| `model` | 默认模型 | 列表第一个 |
| `proxy` | 出站代理 `http://host:port`（暂不支持 socks），留空直连 | `""` |
| `groups` | 分组列表（每组 name/base_url/api_key/models/proxy） | 自动迁移 |

## 参数速查

| 参数 | 可选值 | 说明 |
|---|---|---|
| 模型 | 当前分组模型列表（示例默认 30 个） | ⚙ 设置里维护并可拉取 |
| 尺寸 | auto / 8 种比例 × 1K·2K·4K（1:1~21:9）/ 自定义 WxH | 需为 16 的倍数、比例 1:3~3:1；能否生效由上游决定 |
| 画质 | low / medium / high / auto / xhigh / max | low 省钱提速（实测 423 token vs 默认 1650~3300） |
| 背景 | auto / transparent / opaque | 仅文生图；透明底需 png/webp |
| 格式 | png / jpeg / webp | 上游可能无视此参数仍返回 PNG，程序按魔数嗅探命名 |
| 审核 | auto / low | low = 更宽松 |

## 中转站实测行为

- `quality` 真实生效；`output_format` 常被上游忽略；自定义尺寸部分生效（宽高比保留）
- 中转站对非法参数值不做可靠校验，本地校验（16 倍数、比例、透明底+jpeg 冲突等）已在程序内实现
- 按 token 计费，费率以你的中转站为准；单张约 60~90 秒

## 项目结构

```
├── 启动WebUI.bat        # Windows 双击启动
├── app.py               # 启动入口
├── webui/               # 程序本体
│   ├── server.py        #   HTTP 服务器与启动流程
│   ├── api.py           #   /api/* 端点
│   ├── generate.py      #   生成核心（上游调用/落盘/后台重跑）
│   ├── jobs.py          #   任务注册表与中止
│   ├── network.py       #   出站网络（代理/证书兜底）
│   ├── storage.py       #   配置/收藏/常量
│   └── web/             #   前端源文件（html/css/js）
└── data/                # 用户数据（git 忽略；整机迁移只需拷贝此目录）
    ├── config.json
    ├── favorites.json
    └── outputs/
```

## 从 v1 升级

下载 v2.0.0 覆盖旧目录（或解压到新目录）后启动一次：旧 `config.json` / `favorites.json` / `outputs/` 会自动迁移进 `data/`，原位置文件被移动、不会重复。迁移幂等，可放心重启。

## 常见问题

- **双击 bat 闪退**：在文件夹地址栏输入 `cmd` 回车，再执行 `python app.py` 看具体报错
- **端口被占用**：编辑 `启动WebUI.bat`，把 `python app.py` 改成 `python app.py --port 9000`
- **需要走代理**：⚙ 设置 → 网络代理填 `http://127.0.0.1:端口`；生成日志会打印 `代理=直连/地址` 可确认是否生效
- **改图无反应**：改图必须至少上传一张输入图片
- **拉取模型列表报证书错误**：系统证书库过旧会误报 `certificate has expired`，程序已内置 certifi 兜底；仍报错可 `pip install certifi` 或临时走代理

## 更新日志

所有版本的具体改动见 [CHANGELOG.md](CHANGELOG.md)（新版本在前）。

## License

[MIT](LICENSE)

# SnoAkari gpt-image WebUI

[![Version](https://img.shields.io/badge/version-2.1.0-green)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)

专为本地便捷生图而设计：浏览器里调用 OpenAI 兼容协议（`/v1/images/*`）的图像服务——中转站、各类聚合网关均可接入，文生图、改图、多图融合；中转站快速切换分组，素材统一收藏管理。零依赖纯 Python 标准库，双击即用；密钥只存本机，不经第三方服务器。

~~其实就是开发者本人没米，中转站API又不稳定，为了手里的API能哪个好使切哪个，而搞出来的本地调接口小工具。~~

## 快速开始

```bash
git clone https://github.com/Licne/snoakari-gpt-image-webui.git
cd snoakari-gpt-image-webui
python app.py
```

Windows 双击 `启动WebUI.bat` 即可，浏览器自动打开 http://127.0.0.1:8787。

配置：复制 `config.example.json` 为 `data/config.json`，填入密钥：

```json
{ "api_key": "sk-你的密钥", "base_url": "https://你的中转站地址", "model": "gpt-image-1", "proxy": "" }
```

也可在页面右上角 ⚙ 里改配置，自动获取模型列表。

`data/` 目录为用户数据，含全部本地数据（密钥/收藏/生成图），操作文件时注意不要泄露密钥。

## 功能

- 文生图 / 改图·多图融合
- 后台任务：生成中转入后台继续填参，任务面板看进度、可中止、失败可原参数重试
- 分组管理：多组地址/密钥/模型列表，页顶一键切换，可接任意 OpenAI 协议服务
- 模型系列参数适配：gpt-image 系全参数，其他系列自动隐藏不兼容参数
- 收藏管理：收藏夹分组、本地图片导入、导出/导入跨电脑迁移（zip 导出包，内容哈希去重）

- 隐私遮罩：上班摸鱼模糊全部预览图，单击单张切换，双击放大查看
- 快捷引用改图：历史图片一键把图加进改图输入列表

## 常见问题

- **双击 bat 闪退**：地址栏输入 `cmd` 回车，执行 `python app.py` 看报错
- **端口占用**：改用 `python app.py --port 9000`
- **走代理**：⚙ 设置填 `http://127.0.0.1:端口`

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。

## License

[MIT](LICENSE)

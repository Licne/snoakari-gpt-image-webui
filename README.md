# SnoAkari gpt-image WebUI

[![Version](https://img.shields.io/badge/version-2.0.0-green)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)

零依赖的本地 WebUI：浏览器里调用 NewAPI 中转站的 gpt-image / nano-banana / gemini 等图像模型，文生图、改图、多图融合。纯 Python 标准库，无需 pip 安装。密钥只存本机，不经第三方服务器。

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

之后随时可在页面右上角 ⚙ 里改配置。`data/` 目录已被 git 忽略，含全部本地数据（密钥/收藏/生成图）。

## 功能

- 文生图 / 改图·多图融合（1~16 张输入图）
- 后台任务：生成中转入后台，任务面板看进度、可中止、失败可原参数重试
- 中转站分组：多组地址/密钥/模型列表，页顶一键切换
- 模型系列参数适配：gpt-image 系全参数，其他系列自动隐藏不兼容参数
- 收藏 / 重命名 / 引用 / 隐私遮罩 / 出站代理
- 生成文件名自动带前缀：`档位_模型_分组_时间戳`

## 常见问题

- **双击 bat 闪退**：地址栏输入 `cmd` 回车，执行 `python app.py` 看报错
- **端口占用**：改用 `python app.py --port 9000`
- **走代理**：⚙ 设置填 `http://127.0.0.1:端口`
- **证书报错**：`pip install certifi` 或临时走代理

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。

## License

[MIT](LICENSE)

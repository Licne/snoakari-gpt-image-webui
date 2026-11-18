# Changelog

本项目所有 notable 变更记录于此文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Planned

- 作品管理页：收藏夹（创建/重命名/删除/默认夹）、工作区收藏夹筛选下拉、本地图片导入
- 收藏夹导出/导入：自包含 zip（manifest + 图片本体），跨电脑迁移素材

## [2.0.0] - 2026-11-18

### Changed

- **架构重构**：单文件 `app.py`（约 2000 行）拆分为模块化包 `webui/`（server / api / generate / jobs / network / storage / webindex），`app.py` 仅保留启动入口；前端从 Python 字符串拆为独立源文件 `webui/web/`（index.html / style.css / app.js），启动时内联装配
- 用户数据集中到 `data/` 目录（config.json、favorites.json、outputs/），整机迁移只需拷贝该目录

### Added

- v1 → v2 自动迁移：首次启动将旧版 `config.json` / `favorites.json` / `outputs/` 自动移入 `data/`（幂等，不产生重复文件）

### Fixed

- 修复迁移时目标 `data/` 目录不存在导致 `shutil.move` 静默失败的问题

## [1.3.1] - 2026-11-17

### Fixed

- 生成按钮防快速连点：`genBusy` 同步互斥覆盖全流程（含改图编码大图的异步空窗），此前空窗内连点会重复提交请求

## [1.3.0] - 2026-11-17

### Added

- 失败任务重试：任务面板失败条目新增「重试」按钮，用原始完整参数（含改图输入图）一键后台重跑；完整参数仅失败任务保留，成功/中止即释放；`/api/jobs` 响应剔除 payload 防大图下发
- 版本号体系：新增 `APP_VER` 常量，展示于设置弹窗底部，请求 UA 与 server_version 同步使用
- 设置弹窗限高（88vh）加滚动

## [1.2.0] - 2026-11-17

### Added

- 后台任务：生成中可「转入后台，继续填写参数」；任务面板三行布局（状态+job_id+✕ / 模式·模型·尺寸·耗时 / 提示词缩写）；任务真并行；进行中 ✕ 中止（含结果图下载阶段）、已完成 ✕ 单条移除、清除已完成
- 前台/后台任务分离：生成任务默认前台不进任务面板，大按钮「中止生成」与「转入后台」各司其职

### Fixed

- 后台任务中止无效：任务注册表改为覆盖生成全周期（含下载阶段），下载中点 ✕ 也能真正掐断 socket
- 转后台后状态栏被 Abort 提示覆盖的竞态
- 浏览器断连堆栈噪音：`handle_error` 需定义在 Server 类（此前误放 Handler 类为死代码），QuietServer 实测 RST 断连零堆栈
- 结果图下载 120 秒超时：对齐至 600 秒；下载失败提示图片直链可从中转站取回
- 个别系统证书库过旧导致 SSL 证书误报过期：优先 certifi CA 包，未安装回落系统默认

## [1.1.0] - 2026-11-16

### Added

- 生成文件名前缀：`档位(1k/2k/4k/auto)_模型_分组_时间戳`
- 出站代理：⚙ 设置可配置 http/https 代理，生成日志打印 `代理=直连/地址`
- 尺寸预设升级：8 种比例 × 1K/2K/4K 三档两级下拉

### Changed

- UI 优化：侧栏顶部两行布局、只看收藏改开关按钮、收藏星号只显示在名字前、应用改名 SnoAkari gpt-image WebUI、设置按钮只留图标

## [1.0.0] - 2026-11-15

### Added

- 初始发布：零依赖本地 WebUI（纯 Python 标准库，单文件 app.py），浏览器调用 NewAPI 中转站图像模型
- 文生图 / 改图·多图融合（1~16 张输入图，PNG 蒙版局部重绘）
- 中转站分组管理（每组独立地址/密钥/代理/模型列表，可从接口拉取模型）
- 模型系列参数适配（gpt-image 系全参数；nano-banana/gemini/grok 系仅基础参数）
- 收藏 / 重命名 / 引用 / 本地查看 / 中止请求 / 隐私遮罩 / 参数本地记忆

[Unreleased]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.3.1...v2.0.0
[1.3.1]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Licne/snoakari-gpt-image-webui/releases/tag/v1.0.0

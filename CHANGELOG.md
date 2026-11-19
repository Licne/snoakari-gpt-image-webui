# Changelog

本项目所有 notable 变更记录于此文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [2.2.7] - 2026-11-19

### Added

- 品牌视觉：页头 Logo 与 README 横幅（雪夜微光 · SnoAkari），4K 原图存档于仓库

### Changed

- 页头布局：设置按钮与分组下拉框合并为同一行，高度更紧凑

## [2.2.6] - 2026-11-18

### Added

- 重命名、新建合集、删除合集、删除分组等操作改用应用内自定义弹窗，替代浏览器默认输入框与确认框（支持 Enter 确定 / Esc 取消）

### Fixed

- 修复卡片重命名报错 `TypeError: Cannot set properties of null (setting 'href')`：从历史添加的选择卡片没有下载链接，重命名遍历同名卡片时未做防御

## [2.2.5] - 2026-11-18

### Added

- 结果为 URL 时，任务面板显示「下载中…」阶段，图片落库后才切换为「已完成」

### Fixed

- 修复任务面板「刷新」不生效：新任务完成时自动刷新历史的判断条件写反（恰在新完成时跳过），且 `seenDone` 未声明抛错被静默吞掉；「刷新」现在同时刷新任务列表与历史记录
- 修复设置弹窗切换分组无反应：下拉框变化未同步到编辑索引，现在切换分组正常载入对应配置

## [2.2.4] - 2026-11-18

### Changed

- 从历史添加的卡片移除左上角勾选方框，选中状态由「选择 / ✓ 已选」按钮与高亮边框表达

## [2.2.3] - 2026-11-18

### Fixed

- 修复从历史添加中切换布局后点选图片无视觉反应的问题（状态更新误命中工作区隐藏的同名卡片，现限定在右栏内查找）
- 从历史添加选择交互改为显式按钮：平铺用工作区同款卡片「选择」按钮，列表用右侧「选择」胶囊按钮；避免遮罩模式下点选误触图片遮罩切换

## [2.2.2] - 2026-11-18

### Changed

- 「我的收藏」恢复支持重命名与导出，名称旁显示「默认」徽标（仍不可删除）
- 作品管理描述精简为「聚合作品与素材的资产库」

### Fixed

- 修复平铺视图因缺少 display:grid 导致一行只显示一张图的问题，恢复为与工作区一致的多列卡片

## [2.2.1] - 2026-11-18

### Added

- 作品管理右栏新增列表/平铺视图切换（记忆偏好）：平铺即工作区同款卡片网格，列表为紧凑行
- 「从历史添加」改为右栏内联选择模式：直接在合集预览区勾选图片（点击行/卡片即选），一键批量添加所选，支持 Esc 退出；已移除原弹窗

## [2.2.0] - 2026-11-18

### Changed

- 概念调整：「我的收藏」固定命名、不可重命名，定位为类似其他平台的「喜欢」；新建的收藏夹统一称为「合集」，用于整理生成图片与素材库
- 作品管理侧栏：「我的收藏」置顶独立展示（⭐ 标识），其余合集归入「合集」分组；新建/重命名/删除文案同步为合集
- 星标仅表示图片在「我的收藏」中（工作区点★即进入我的收藏）

## [2.1.4] - 2026-11-18

### Changed

- 作品管理右栏图片改为紧凑列表（小缩略图 + 文件名 + 尺寸/大小 + 下载/移出），双击缩略图放大预览
- 「从历史添加」弹窗同步改为列表样式

### Fixed

- 从历史添加弹窗无法正常关闭：补上 ✕ 按钮、点击遮罩关闭、Esc 关闭三种方式
- 修复预览灯箱层级低于弹窗导致在弹窗内双击图片后界面被黑色图层卡住的问题（灯箱 z-index 50→80）

## [2.1.3] - 2026-11-18

### Changed

- 作品管理页改为左右布局：左侧收藏夹列表与管理操作（新建/导入包/导出全部、重命名/导出/删除），右侧为选中收藏夹的图片列表
- 作品管理图片卡片移除「引用」操作，保留下载与移出

## [2.1.2] - 2026-11-18

### Added

- 隐私遮罩覆盖作品管理页：页顶返回栏新增遮罩开关，与工作区状态联动、行为一致（模糊/单击切换/双击放大）

## [2.1.1] - 2026-11-18

### Changed

- 作品管理改整页模式：入口按钮移至「遮罩」开关左侧，进入后隐藏左侧参数栏、整页展示，左上角「← 返回工作区」切回
- 「只看收藏」按钮与收藏夹筛选下拉统一为 28px 高度

## [2.1.0] - 2026-11-18

### Added

- **作品管理**（页顶新增「工作区 / 作品管理」视图切换）：
  - 收藏夹管理：新建 / 重命名 / 删除（默认夹「我的收藏」不可删、可改名）；删除收藏夹只解除关联，不删 outputs/ 图片
  - 收藏夹详情：浏览夹内图片，支持引用（加入改图输入）、下载、移出
  - 导入图片：把本地图片导入到指定收藏夹（复制进 outputs/ 统一存放，支持中文文件名）
  - 从历史添加：选择器网格从 outputs/ 历史中批量加入当前夹
  - 一张图可属于多个收藏夹
- **收藏夹导出 / 导入**：导出自包含 zip（manifest.json + 图片本体，按单夹或全部导出）；导入自动识别导出包——同名收藏夹合并、文件按内容哈希去重（同内容跳过、同名不同内容自动加后缀），完成后弹汇总（新建/合并夹数、新增/跳过张数）
- 工作区历史区新增收藏夹筛选下拉（默认不筛选），与「只看收藏」并存
- 工作区「收藏」星标直达默认收藏夹；图片重命名后所有收藏夹条目自动跟随

### Changed

- 收藏数据从 favorites.json（单一清单）升级为 collections.json（多收藏夹结构）；首次启动自动把旧收藏迁移进默认夹「我的收藏」，旧文件保留不动

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

[2.2.4]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.1.4...v2.2.0
[2.1.4]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.3.1...v2.0.0
[1.3.1]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Licne/snoakari-gpt-image-webui/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Licne/snoakari-gpt-image-webui/releases/tag/v1.0.0

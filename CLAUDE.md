# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CrossPost：从 YouTube 抓取短视频 → 转码 / ASR / 翻译 / 烧录中文字幕 → 发布到头条、百家号、小红书。单机、个人、无人值守。

## 命令

```bash
uv sync                                   # 安装依赖；需要浏览器发布再加 --extra browser，并执行 playwright install chromium
cp config.example.yaml config.yaml        # config.yaml 从当前工作目录读取，不入库
uv run python -m crosspost                # 启动：先跑一次完整轮询，再进入 APScheduler 循环
uv run crosspost-web --port 8086          # 本地仪表盘（默认只绑 127.0.0.1，无鉴权）

uv run pytest                                                   # 全部测试
uv run pytest tests/test_publisher.py::test_name -v             # 单个测试
```

测试不依赖 FFmpeg、网络或模型：外部调用都在各模块的导入位置被 `patch`（例如 `crosspost.processor.transcode_to_h264`），数据库用 `conftest.py` 里的内存 SQLite fixture。真实运行需要 PATH 里有 `ffmpeg`/`ffprobe`，并且在 `processing.font_path` 放一个 CJK 字体——`src/crosspost/assets/fonts/` 里只有 `.gitkeep`。

## 架构

完整设计见 `docs/ARCHITECTURE.md`（描述的是实际实现，不是 `docs/research/` 里早期 Celery 方案）。要点：

- **单进程、同步流水线**。`scheduler.poll_and_download_job` 是唯一的定时任务，按顺序调用 `feeds` → `downloader` → `processor` → `publisher`。没有队列，也没有 worker。
- **数据库就是状态机**。`models.Content.status`：`DISCOVERED → DOWNLOADING → DOWNLOADED → PROCESSED → TRANSLATED → PUBLISHED`，任何阶段都可能进入 `FAILED`。每个阶段只查询处于前一状态的行，所以重启后会自动续跑；`recover_incomplete_downloads` 负责把卡在 `DOWNLOADING` 的行重置。
- **处理步骤以产物路径实现幂等**。`processor._process_single` 发现 `processed_video_path`、`srt_path`、`translated_srt_path`、`ass_path` 已有值就跳过对应步骤；转码和 ASR 在一个双线程池里并行，每步都用 tenacity 重试。
- **任务函数要能 pickle**。`poll_and_download_job` 只接收 `settings`，engine 在函数内部重建，因为 SQLAlchemy Engine 不能 pickle，放不进 APScheduler 的 job store。
- **发布层靠配置驱动，不按平台分类**。`publisher.create_publisher` 根据 YAML 里的 `backend`（`api` / `browser` / `dry_run`）选实现；平台差异写在配置里，接入新平台一般只需加 YAML。`PublishRecord` 记录每个（内容，平台）组合的状态，负责限流（`min_interval_minutes`）、指数退避和幂等。
- **翻译分两路**：字幕逐句走 DeepL，标题和描述走 Anthropic Claude。
- `web.py` 用标准库 `http.server` 写成，除了只读仪表盘，还能手动提交链接、在后台线程触发一次流水线（用 `threading.Lock` 防止重入）。

## 项目状态与约定

- Phase 1、2 已验证。Phase 3（发布）代码写完了，但**没有在真实平台上联调过**：API endpoint 还是占位符，小红书选择器没调过。改发布逻辑时先用 `backend: dry_run` 跑。进度以 `docs/STATUS.md` 为准。
- 用 GSD 工作流：`.planning/` 放实时状态（STATE.md、ROADMAP.md、phases/），`docs/` 是审计后的可读副本。完成一个阶段或计划时，要同步更新这两处。
- 仓库装了自动备份 hook，会定期生成 `Auto-backup: <时间戳>` 提交，看 git 历史时要知道这一点。

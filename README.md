# CrossPost - 跨平台内容搬运工具

一个全自动的跨平台内容搬运工具，从 YouTube 抓取视频和 Shorts，自动转码、语音识别、翻译并烧录中文字幕，发布到国内主流平台（今日头条、百家号、小红书等）。面向个人内容创作者，部署在云服务器上长期无人值守运行。

> 项目文档主体维护在 [`docs/`](docs/) 目录（PROJECT.md / ARCHITECTURE.md / REQUIREMENTS.md / ROADMAP.md / STATUS.md），本文件是面向快速上手的摘要。GSD 工作流的实时状态文件仍在 [`.planning/`](.planning/)（隐藏目录），`docs/` 是对照代码审计后的可读副本。

## 当前进度

**总体：Phase 1、2 已完成并验证；Phase 3（发布）代码已写完，但未经真实平台验证，也未走 GSD 计划流程。** 详见 [`docs/STATUS.md`](docs/STATUS.md)。

| Phase | 内容 | 状态 |
|-------|------|------|
| 1. Pipeline Foundation | 状态机、配置、调度、YouTube 抓取 | ✅ 已完成并验证（3/3） |
| 2. Content Processing | 转码、ASR、字幕烧录、翻译 | ✅ 已完成并验证（5/5） |
| 3. Publishing & Automation | 各平台发布、防风控、自动化加固 | 🟡 代码完成，未经真实平台验证 |

### 已完成需求（v1）

**内容获取**
- [x] 通过 YouTube RSS 监控指定频道的新视频和 Shorts
- [x] 通过 yt-dlp 下载视频（含标题、描述、缩略图等元数据）
- [x] 频道列表可通过 YAML 配置文件管理
- [x] 按时长过滤，默认只下载 ≤ 3 分钟的视频

**内容处理**
- [x] faster-whisper 本地 ASR 提取英文字幕（SRT）
- [x] 英文字幕翻译成中文（DeepL，句子级，保留时间轴）
- [x] 中文字幕烧录到视频（CJK 字体，横竖屏适配）
- [x] 标题/描述用 LLM（Claude）翻译成自然中文
- [x] 按平台规格转码视频（H.264 MP4，分辨率/码率自适应）

**自动化**
- [x] APScheduler 定时轮询 YouTube 频道
- [x] SQLite 去重，防止重复下载/处理
- [x] 任务状态机（DISCOVERED → DOWNLOADED → PROCESSED → TRANSLATED → PUBLISHED/FAILED），崩溃可恢复

### Phase 3 需求（代码已写完，未经真实平台验证）

- [x] 自动发布到今日头条（头条号 API）—— 代码就绪，`config.example.yaml` 里的 endpoint 仍是占位符，未联调
- [x] 自动发布到百度百家号（API）—— 同上，未联调
- [x] 自动发布到小红书（Playwright 浏览器自动化）—— 代码就绪，选择器未针对真实页面调试过
- [x] 发布间隔控制（按平台配置最小发布间隔，避免风控）—— 已完成且有测试覆盖

上线前请先用 `backend: dry_run` 跑通队列/限流逻辑，再逐平台切换到真实配置并小流量验证。

详细的需求追踪表见 [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)，完成状态总览见 [`docs/STATUS.md`](docs/STATUS.md)。

## 快速开始

```bash
# 安装依赖（使用 uv）
uv sync

# 复制配置模板并填写频道 ID / API Key
cp config.example.yaml config.yaml

# 运行
uv run python -m crosspost
```

配置项说明见 [`config.example.yaml`](config.example.yaml)，包含频道列表、下载参数、调度间隔、各平台发布配置等。

## 项目结构

```
src/crosspost/
├── __main__.py       # 应用入口（调度循环）
├── config.py          # YAML 配置加载（AppSettings）
├── models.py           # SQLModel 数据模型 / 状态机
├── database.py         # 数据库引擎与初始化
├── feeds.py             # YouTube RSS 轮询
├── downloader.py        # yt-dlp 下载
├── transcoder.py        # FFmpeg 转码
├── transcriber.py       # faster-whisper ASR
├── translator.py        # DeepL / Claude 翻译
├── subtitler.py          # 双语 ASS 字幕生成 + 烧录
├── processor.py          # 处理管线编排
├── scheduler.py           # APScheduler 调度与崩溃恢复
├── publisher.py           # 平台发布（代码完成，未经真实平台验证，见 docs/STATUS.md）
└── web.py                  # crosspost-web 入口（本地仪表盘，范围外新增能力，见 docs/REQUIREMENTS.md）
```

## 技术栈

Python 3.12+ · yt-dlp · faster-whisper · DeepL / Anthropic Claude · FFmpeg (pysubs2) · SQLModel + SQLite · APScheduler · Playwright（浏览器自动化发布）

## 范围外（Out of Scope）

多用户/SaaS、直播搬运、评论区互动运营、AI 原创内容生成、平台数据分析回收、分布式多机部署 —— 详见 [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) 中的 Out of Scope 表。

> 注：原计划中"Web 管理界面"也在范围外，但代码库里已经有 `web.py` 实现了本地仪表盘，属于范围之外的既成事实，详见 `docs/REQUIREMENTS.md`。

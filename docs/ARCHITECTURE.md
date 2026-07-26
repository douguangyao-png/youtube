# Architecture: CrossPost（现状设计文档）

**记录时间：** 2026-07-26
**依据：** `src/crosspost/` 实际代码 + `.planning/research/ARCHITECTURE.md` 早期研究结论

> 早期研究文档（[research/ARCHITECTURE.md](research/ARCHITECTURE.md)）设想了一套 Celery + Redis 的任务队列架构，每个平台一个 publisher 文件。实际实现为了个人单机部署的简单性，选择了更轻量的方案。本文档描述**实际构建**的架构，供后续开发/排障参考。

## 系统总览

```
┌────────────────────────────────────────────────────────────┐
│                    APScheduler (scheduler.py)               │
│        单一定时任务 poll_and_download_job，按 schedule       │
│        .poll_interval_minutes 周期触发（默认 30 分钟）        │
└───────────────────────────┬──────────────────────────────────┘
                             │ 同步顺序调用（进程内，无消息队列）
                             ▼
  ①feeds.py ──▶ ②downloader.py ──▶ ③processor.py ──▶ ④publisher.py
  RSS 发现新视频   yt-dlp 下载          编排转码/ASR/翻译/烧录     按平台发布
                                     (transcoder/transcriber/
                                      translator/subtitler)
                             │
                             ▼
              ┌──────────────────────────────┐
              │   SQLite (models.py + database.py)│
              │   Content 状态机 + PublishRecord   │
              └──────────────────────────────┘
                             ▲
                             │ 读/写状态、手动入队
              ┌──────────────────────────────┐
              │   web.py (crosspost-web)      │
              │   本地仪表盘 + 手动提交表单       │
              └──────────────────────────────┘
```

与早期研究方案的关键差异：

| 维度 | 早期研究设想 | 实际实现 |
|------|-------------|----------|
| 任务分发 | Celery + Redis 队列，各阶段异步任务 | 单进程内同步函数调用链，由 APScheduler 定时触发整条流水线 |
| Publisher | 每平台一个文件（`douyin.py`/`toutiao.py`/...） | 单个通用 `Publisher` 抽象类，`backend` 字段（`api`/`browser`/`dry_run`）驱动行为，平台差异全部下沉到 YAML 配置 |
| 并发 | 多 worker 并行处理多条内容 | 单线程顺序处理；Web 面板的手动触发会在后台线程里跑一次流水线，用 `threading.Lock` 防止并发重入 |
| 抖音 (Douyin) | 规划在内的发布目标 | 未实现（在 v2 待办 PUB-04），当前只做头条/百家号/小红书 |

选择更简单方案的原因：单机个人使用，视频量小，不需要队列系统带来的运维复杂度；牺牲的是水平扩展能力，换来的是代码量和部署成本的大幅降低。

## 模块职责

| 模块 | 职责 |
|------|------|
| `config.py` | 用 Pydantic Settings 从 YAML 加载全部配置：频道列表、下载/处理/发布/调度参数 |
| `models.py` | SQLModel 定义 `Content`（内容状态机）与 `PublishRecord`（逐平台发布记录） |
| `database.py` | SQLite engine 创建与建表 |
| `feeds.py` | 轮询 YouTube RSS，发现新视频/Shorts，写入 `DISCOVERED` 状态 |
| `downloader.py` | yt-dlp 下载视频+元数据+缩略图，按时长过滤，写入 `DOWNLOADED` |
| `transcoder.py` | FFmpeg 转码为 H.264 MP4，动态码率/分辨率适配 |
| `transcriber.py` | faster-whisper 本地 ASR，生成英文 SRT |
| `translator.py` | DeepL 批量翻译字幕（句子级），Claude 翻译标题/描述 |
| `subtitler.py` | pysubs2 生成双语 ASS 字幕，FFmpeg 烧录进视频，写入 `PROCESSED`/`TRANSLATED` |
| `processor.py` | 编排 transcoder → transcriber → translator → subtitler 的顺序执行与重试 |
| `publisher.py` | 按平台配置发布（API 或 Playwright 浏览器自动化），限流、重试、退避、状态写回 |
| `scheduler.py` | APScheduler 定时任务定义、崩溃恢复（重新拾取中间状态的行）、把各阶段串联成一次完整轮询 |
| `web.py` | 只读仪表盘 + 手动提交 YouTube 链接入队 + 一次性触发流水线（详见 [REQUIREMENTS.md](REQUIREMENTS.md) 中"需求之外新增的能力"） |
| `__main__.py` | 应用入口，启动调度循环 |

## 数据模型

`Content` 状态机（`models.py`）：

```
DISCOVERED → DOWNLOADING → DOWNLOADED → PROCESSED → TRANSLATED → PUBLISHED
                                                          │
                                                          └──────────▶ FAILED（任意阶段失败）
```

`PublishRecord` 是 `Content` 与平台的多对多关联表，每个（内容, 平台）组合一条记录，独立追踪 `PENDING/PUBLISHING/PUBLISHED/FAILED/SKIPPED` 状态、重试次数、下次可尝试时间——这是 AUTO-04（发布间隔控制）和失败重试退避的落地位置。

## 发布层设计（`publisher.py`）

- `Publisher` 抽象基类 + 三个实现：`DryRunPublisher`（只记录不外发，用于联调）、`ApiPublisher`（JSON over HTTP，用于头条/百家号）、`BrowserPublisher`（Playwright，用于小红书）。
- `create_publisher(platform, cfg)` 按配置里的 `backend` 字段选择实现，不需要为新平台写新类——只要新平台能用现成的 API 或浏览器表单模式，加一段 YAML 配置即可接入。
- 限流：`_rate_limit_allows` 检查同平台上一次成功发布时间 + `min_interval_minutes` 是否已过。
- 重试：失败后进入指数退避（`min(60, 2**attempts)` 分钟），超过 `max_retries` 后标记 `FAILED` 并停止阻塞其他内容。
- 幂等：`_get_or_create_record` 保证同一（内容, 平台）只有一条记录，重复调用不会重复发布已成功的项。

## 已知设计局限 / 后续待办

- 单进程同步执行意味着一次 ASR/转码任务会阻塞整条轮询；数据量增长后需要考虑任务队列化（早期研究文档里的方案可以直接复用）。
- `ApiPublisher`/`BrowserPublisher` 目前是通用骨架，字段名和选择器完全依赖使用者手填 `config.yaml`，没有针对头条/百家号/小红书的专属容错（例如小红书的滑块验证码、头条的 Token 刷新）——上线前必须实测。
- Web 面板没有鉴权，仅设计为绑定 `127.0.0.1` 本地访问；如果要暴露到公网需要补充认证。

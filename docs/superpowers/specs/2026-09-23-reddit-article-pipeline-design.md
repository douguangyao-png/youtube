# Reddit 热帖编译 → 国内平台图文草稿（Phase A）设计

**日期：** 2026-09-23
**状态：** 待用户审核

## 目标

从指定 Reddit 子版块抓取 AI / 技术类高赞、高回复帖子，翻译成中文并加上编者点评，为 今日头条、百度百家号、知乎、微信公众号 各生成一份标题和篇幅不同的图文草稿。草稿在本地仪表盘人工审核后，由用户手动复制发布。

## 已确认的决策

| 决策 | 结论 |
|------|------|
| 发布方式 | 只生成草稿，人工审核，手动发布；不自动发布 |
| 首批平台 | 头条、百家号、知乎、公众号 |
| 来源 | 配置里的固定子版块列表 + 点赞/评论数门槛 |
| 内容形式 | 编译 + 点评（导读、原帖编译、精选评论、编者点评、来源声明） |
| 架构 | 方案 A：与视频流水线并行的独立文本流水线，共享配置、数据库、调度、仪表盘，不改视频代码 |
| 范围 | 本期只做文字草稿；图片卡片（B）、视频（C，含 YouTube）后续单独立项 |

## 数据流

```
poll_reddit_job（APScheduler 独立任务）
  reddit.py         抓取 top/day → 过滤 → 排序 → 选评论 → Article(DISCOVERED)
  article_writer.py ① 共享翻译 + 点评要点 + 敏感度
                    ② 四个平台各写一版 → ArticleDraft(PENDING_REVIEW)，Article(DRAFTED)
web_articles.py     预览 / 编辑 / 通过 / 拒绝 / 重新生成 / 复制 / 标记已发布
```

## 数据模型（`models.py` 新增两张表，`create_all` 自动建表）

**`Article`**（每个 Reddit 帖子一行）
- `reddit_id`（唯一）、`subreddit`、`permalink`、`author`、`created_utc`、`score`、`num_comments`
- `title_en`、`body_en`、`comments_json`（作者、赞数、回复数、正文、层级）
- `translation_json`：中文标题、正文、评论译文、点评要点、敏感度
- `status`：`DISCOVERED → DRAFTED`，或 `FAILED` / `SKIPPED`
- `error_message`、`discovered_at`、`drafted_at`

**`ArticleDraft`**（(article_id, platform) 唯一）
- `platform`：`toutiao` / `baijiahao` / `zhihu` / `wechat`
- `format`：本期固定 `text`，预留 `images` / `video`
- `title`、`summary`、`body_markdown`、`extra_json`（3 个候选标题等）、`assets_json`（本期为空）
- `status`：`PENDING_REVIEW → APPROVED → PUBLISHED`，或 `REJECTED`；另有 `REGENERATING`、`FAILED`
- `review_note`、`published_url`、`reviewed_at`、`published_at`

## 抓取与筛选（`reddit.py`）

配置：

```yaml
reddit:
  enabled: true
  poll_interval_minutes: 360
  user_agent: "crosspost/0.1 by <reddit 用户名>"
  client_id: ""          # 可选；填了走 OAuth，云服务器 IP 常被未登录请求 403
  client_secret: ""
  max_articles_per_run: 5
  defaults: { min_score: 300, min_comments: 80 }
  subreddits:
    - { name: ClaudeAI }
    - { name: OpenAI }
    - { name: LocalLLaMA }
    - { name: singularity, min_score: 1000 }
    - { name: programming }
  blocked_keywords: []   # 中文译文命中则跳过
```

- 帖子：`r/{sub}/top.json?t=day`；评论：`{permalink}.json?sort=top`。
- 过滤顺序：置顶 / NSFW / 已删除 → 只保留文字帖和带讨论的链接帖（纯图、视频帖记 `SKIPPED`）→ 门槛（子版块可覆盖）→ 按 `reddit_id` 去重，跨版转发按原帖去重 → 按 `score + 3 × num_comments` 排序取前 `max_articles_per_run`。
- 评论：排除 AutoModerator、已删除、少于 20 字符；按赞数取顶层评论，并补入回复数多的；每条最多带 2 条高赞回复；每帖最多存 15 条候选。

## 翻译与分平台写作（`article_writer.py`）

每篇 1 + 4 次 Claude 调用，均返回结构化 JSON 并用 pydantic 校验。模型可配置，默认 `claude-sonnet-5`。

**① 共享翻译**：中文标题、正文、评论译文（模型和产品名保留英文）；3–5 条点评要点；敏感度 `ok / review / block` 及原因。`block` 或命中 `blocked_keywords` → `SKIPPED`；`review` → 审核页显示警告。

**② 平台版本**，统一结构：导读 → 原帖编译 → 网友热评（带赞数，保留回复链和楼主回复）→ 【编者点评】 → 来源（“编译自 Reddit r/xxx，原帖链接…，本文由 AI 辅助翻译”）。平台差异放在配置 `article_profiles` 里：

| | 头条 | 百家号 | 知乎 | 公众号 |
|---|---|---|---|---|
| 标题 | 20–30 字，悬念 / 对比，禁止标题党 | 含可搜索的模型 / 产品名，陈述式 | 提问或亮观点 | ≤30 字，另附 ≤120 字摘要 |
| 正文 | 800–1500 字，短段落 | 1000–2000 字，小标题 | 2000–3500 字，深度分析 | 1500–2500 字，导读 + 小标题 |
| 评论数 | 3–5 | 4–6 | 8–12，正反观点 | 5–8 |
| 结尾 | 提问引导评论 | 总结 | 开放问题 | 引导关注 |

- 每版生成 3 个候选标题。
- 提示词要求：原帖和评论里的说法一律标明出处（“原帖称”“有网友表示”）；点评不得新增数字、跑分或发布信息。
- 重新生成时把审核备注传入提示词，只重写该平台草稿，不重做翻译。

## 审核页（新模块 `web_articles.py`，`web.py` 只做路由转发）

- `/articles`：按状态筛选；每行显示子版块、赞数、评论数、敏感度警告、四个平台草稿状态；「立即抓取 Reddit」按钮（后台线程 + 锁）。
- `/articles/<id>`：左栏英文原帖与评论（可折叠）和原链接；右栏四个平台标签页，含候选标题切换、标题 / 摘要 / 正文编辑、保存后服务端渲染预览、字数对照、按钮（保存、通过、拒绝、重新生成（附备注）、复制标题、复制富文本、复制 Markdown、标记已发布（填链接））。
- 富文本复制用 Clipboard API，失败时退回选区复制；Markdown 渲染新增依赖 `markdown`。
- 仪表盘仍只绑定 127.0.0.1，云服务器通过 SSH 隧道访问（`ssh -L 8086:127.0.0.1:8086 <服务器>`）。
- 所有操作为 POST，完成后带提示跳回原页面。重新生成和重试在后台线程执行。

本期不做：登录鉴权、定时发布、批量操作、页面内富文本编辑器、平台自动发布。

## 错误处理

- 单个子版块失败只记日志并跳过；429 / 5xx 用 tenacity 退避重试；403 在日志里提示配置 OAuth。
- Claude 调用出错用 tenacity 重试；JSON 校验失败重试一次，仍失败则 Article 记 `FAILED`，可在审核页重试。
- 单个平台版本失败只影响该草稿。
- 未配置 Anthropic key：启动时报错提示，跳过写作步骤，抓取照常。
- 幂等：已有 `translation_json` 则跳过 ①；只补齐缺失的平台草稿。启动时把 `REGENERATING` 恢复为 `PENDING_REVIEW`。
- Reddit 任务和视频任务各自 try/except，互不影响。
- `get_engine` 目前没有设置 SQLite 忙等超时，而调度进程和仪表盘进程会同时写库；对 SQLite 增加 `connect_args={"timeout": 30}`。

## 测试

pytest，不访问真实网络，不调用真实 Claude：
- `reddit.py`：`tests/fixtures/reddit/` 存裁剪过的真实 JSON，覆盖过滤、门槛与子版块覆盖、排序、跨版转发去重、评论选择。
- `article_writer.py`：mock Anthropic 客户端，覆盖提示词包含平台配置和审核备注、JSON 异常 → 重试 → `FAILED`、`block` → `SKIPPED`、单平台失败隔离、重复运行幂等。
- `web_articles.py`：内存数据库，覆盖页面渲染和各 POST 操作。
- `config.py` / `scheduler.py`：新配置的默认值与校验；仅在 `reddit.enabled` 时注册任务。

**验收：** 连真实 Reddit 和 Claude 跑一次，至少一篇生成 4 份草稿；在仪表盘审核后，复制到头条编辑器，格式保持正常。

## 后续阶段（不在本期范围）

- **B 图片卡片**：HTML 模板 + Playwright 截图，生成 3:4 / 9:16 卡片组，面向小红书、微博、微头条。
- **C 视频**：卡片 + TTS 配音 + 字幕 + 免版权背景音乐，FFmpeg 合成；面向抖音、视频号、B站、西瓜；另出 YouTube 版，通过 Data API v3 上传，默认私密，由用户手动公开。视频需标注 AI 配音，YouTube 上传时勾选合成内容声明。

## 风险

- 各平台收益与原创规则变化频繁，上线前需到各创作者中心核实。
- Reddit 数据 API 限制商业用途，规模化变现前需评估条款。
- AI 生成内容需按《人工智能生成合成内容标识办法》标注。

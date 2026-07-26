# CrossPost - 跨平台内容搬运工具

> 本文件为项目最初的定义文档（原 `.planning/PROJECT.md`），记录产品目标与背景约束。
> 实时的开发进度与需求完成情况见 [STATUS.md](STATUS.md)；`.planning/` 中的同名文件是 GSD 工作流的实时状态源，本目录下的版本是面向阅读的归档副本。

## What This Is

一个全自动的跨平台内容搬运工具，从 YouTube 和 X (Twitter) 抓取视频、短视频和图文内容，自动翻译成中文后发布到国内主流平台（抖音、头条、小红书、百度）。面向个人内容创作者使用，部署在云服务器上长期运行。

## Core Value

自动化完成从海外内容抓取到国内平台发布的全流程，包括下载、转码、翻译、适配和发布，无需人工干预。

## 需求概览

v1 范围内的功能需求、完成状态与实现方式见 [REQUIREMENTS.md](REQUIREMENTS.md)。

## Context

- **内容来源 API 情况**：YouTube 有 Data API（下载用 yt-dlp），X API 有付费限制（可能需要爬虫辅助）
- **国内平台发布情况**：
  - 抖音：有开放平台 API（需企业认证），个人可用浏览器自动化
  - 头条：头条号有发布 API
  - 小红书：无公开发布 API，需浏览器自动化
  - 百度百家号：有内容发布 API
- **翻译方案**：可用 LLM API（如 Claude/GPT）或专业翻译 API（如 DeepL）
- **视频字幕**：需要 ASR（语音识别）+ 翻译 + 字幕烧录
- **合规风险**：内容版权、平台规则、账号风控需要注意

## Constraints

- **Tech Stack**: Python — 用户指定
- **部署环境**: 云服务器，需要能运行 headless 浏览器
- **网络**: 需要能访问 YouTube 和 X（可能需要代理）
- **发布方式**: 混合方案 — 有 API 用 API，没有的用 Playwright/Selenium 浏览器自动化
- **翻译成本**: 需要控制 API 调用成本

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 技术栈 | 用户偏好，且生态丰富（yt-dlp, Playwright 等） | 已实施 — Phase 1-3 均基于 Python 3.12 |
| 混合发布方案 | 部分平台有 API，部分需要浏览器自动化 | 已实施 — `publisher.py` 支持 `api`/`browser`/`dry_run` 三种 backend |
| 全自动模式 | 个人使用，追求效率 | 已实施 — APScheduler 轮询 + 全流程自动衔接（下载→处理→翻译→发布） |
| yt-dlp 下载视频 | 成熟稳定的 YouTube 下载方案 | 已实施 |

---
*原始定义日期：2026-03-14。归档于 2026-07-26，内容未改写，仅补充了指向状态文档的说明。*

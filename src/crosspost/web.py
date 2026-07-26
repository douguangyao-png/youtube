"""Read-only local dashboard for CrossPost state."""

from __future__ import annotations

import argparse
import html
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from crosspost.config import AppSettings
from crosspost.database import get_engine, init_db
from crosspost.models import Content, ContentStatus, PublishRecord, PublishStatus
from crosspost.scheduler import poll_and_download_job


CONTENT_STATUS_ORDER = [
    ContentStatus.DISCOVERED,
    ContentStatus.DOWNLOADING,
    ContentStatus.DOWNLOADED,
    ContentStatus.PROCESSED,
    ContentStatus.TRANSLATED,
    ContentStatus.PUBLISHED,
    ContentStatus.FAILED,
]

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True)
class DashboardModel:
    """Data required to render the dashboard."""

    database_url: str
    items: list[Content]
    content_counts: dict[ContentStatus, int]
    publish_counts: dict[PublishStatus, int]
    publish_records: dict[int, list[PublishRecord]]
    total: int
    selected_status: str
    generated_at: datetime
    base_path: str = ""
    flash: str = ""
    view: str = "overview"


def build_dashboard_model(
    engine: Engine,
    database_url: str,
    status: str = "all",
    base_path: str = "",
    flash: str = "",
    view: str = "overview",
) -> DashboardModel:
    """Load content and publish state for dashboard rendering."""
    selected_status = status if status in {s.value for s in ContentStatus} else "all"

    with Session(engine) as session:
        all_items = session.exec(
            select(Content).order_by(Content.discovered_at.desc(), Content.id.desc())
        ).all()
        all_records = session.exec(
            select(PublishRecord).order_by(PublishRecord.updated_at.desc())
        ).all()

    content_counts = {state: 0 for state in CONTENT_STATUS_ORDER}
    for item in all_items:
        content_counts[item.status] += 1

    publish_counts = {state: 0 for state in PublishStatus}
    publish_records: dict[int, list[PublishRecord]] = {}
    for record in all_records:
        publish_counts[record.status] += 1
        publish_records.setdefault(record.content_id, []).append(record)

    items = all_items
    if selected_status != "all":
        items = [item for item in all_items if item.status.value == selected_status]

    return DashboardModel(
        database_url=database_url,
        items=items,
        content_counts=content_counts,
        publish_counts=publish_counts,
        publish_records=publish_records,
        total=len(all_items),
        selected_status=selected_status,
        generated_at=datetime.now(),
        base_path=base_path.rstrip("/"),
        flash=flash,
        view=view,
    )


def enqueue_video_url(engine: Engine, video_url: str) -> tuple[Content, bool]:
    """Create a manual DISCOVERED item from a YouTube URL.

    Returns the content row and whether it was newly created.
    """
    video_id = extract_youtube_video_id(video_url)
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"

    with Session(engine) as session:
        existing = session.exec(select(Content).where(Content.video_id == video_id)).first()
        if existing:
            if existing.status == ContentStatus.FAILED:
                existing.status = ContentStatus.DISCOVERED
                existing.error_message = None
                existing.failed_at = None
                existing.video_url = canonical_url
                session.add(existing)
                session.commit()
                session.refresh(existing)
            return existing, False

        content = Content(
            video_id=video_id,
            channel_id="manual",
            title="Manual submission",
            video_url=canonical_url,
            status=ContentStatus.DISCOVERED,
        )
        session.add(content)
        session.commit()
        session.refresh(content)
        return content, True


def extract_youtube_video_id(value: str) -> str:
    """Extract a YouTube video ID from a URL or raw ID."""
    candidate = value.strip()
    if YOUTUBE_ID_RE.match(candidate):
        return candidate

    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"youtu.be", "www.youtu.be"} and path_parts:
        video_id = path_parts[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif path_parts and path_parts[0] in {"shorts", "embed", "live"} and len(path_parts) > 1:
            video_id = path_parts[1]
        else:
            video_id = ""
    else:
        video_id = ""

    if not YOUTUBE_ID_RE.match(video_id):
        raise ValueError("请输入有效的 YouTube 视频链接")
    return video_id


def render_dashboard(model: DashboardModel) -> str:
    """Render the dashboard as a standalone HTML document."""
    cards = "\n".join(_render_status_card(status, model) for status in CONTENT_STATUS_ORDER)
    rows = "\n".join(_render_content_row(item, model.publish_records.get(item.id or -1, [])) for item in model.items)
    flash_html = _render_flash(model.flash)
    cards_section = f"""
    <section class="cards" aria-label="状态概览">
      {cards}
    </section>
    """ if model.view == "overview" else ""
    empty_state = """
      <tr>
        <td colspan="8" class="empty">当前没有匹配内容。先运行后台任务，或切换状态筛选。</td>
      </tr>
    """
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CrossPost Dashboard</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --surface: #ffffff;
      --surface-2: #eef4f7;
      --ink: #15202b;
      --muted: #667789;
      --soft: #8a98a8;
      --line: #d8e2ea;
      --line-strong: #bdcbd7;
      --accent: #0d9488;
      --accent-2: #e11d48;
      --accent-3: #f59e0b;
      --navy: #213547;
      --shadow: 0 18px 48px rgba(33, 53, 71, .11);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Aptos", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{
      max-width: 1420px;
      margin: 0 auto;
      padding: 26px 24px 42px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: stretch;
      margin-bottom: 16px;
    }}
    .identity {{ min-width: 310px; padding-top: 2px; }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .eyebrow::before {{
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 5px rgba(13, 148, 136, .12);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(31px, 4.6vw, 58px);
      line-height: .96;
      letter-spacing: 0;
      font-weight: 850;
    }}
    .subtitle {{
      max-width: 560px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }}
    .nav {{
      display: flex;
      gap: 6px;
      margin-top: 18px;
    }}
    .nav-link {{
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px 10px;
      background: var(--surface);
      color: var(--muted);
      font-size: 12px;
      font-weight: 850;
    }}
    .nav-link.active {{
      background: var(--navy);
      border-color: var(--navy);
      color: #fff;
    }}
    .meta {{
      flex: 1;
      display: grid;
      grid-template-columns: repeat(3, minmax(150px, 1fr));
      gap: 10px;
      min-width: 520px;
    }}
    .summary {{
      min-height: 118px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 16px;
      box-shadow: 0 8px 24px rgba(33, 53, 71, .06);
    }}
    .summary-label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    .summary-note {{
      margin-top: 9px;
      color: var(--soft);
      font-size: 12px;
      line-height: 1.45;
    }}
    .metric {{
      display: block;
      margin-top: 14px;
      color: var(--navy);
      font-size: 34px;
      font-weight: 850;
      line-height: 1;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(142px, 1fr));
      gap: 10px;
      margin: 20px 0 18px;
    }}
    .card {{
      position: relative;
      min-height: 94px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 14px 14px 13px;
      box-shadow: 0 8px 22px rgba(33, 53, 71, .06);
      transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
      overflow: hidden;
    }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: var(--line-strong);
    }}
    .card:hover {{
      transform: translateY(-2px);
      border-color: var(--line-strong);
      box-shadow: var(--shadow);
    }}
    .card.active {{
      border-color: rgba(13, 148, 136, .42);
      background: linear-gradient(180deg, #ffffff, #edfdfa);
    }}
    .card.active::before {{ background: var(--accent); }}
    .card:nth-child(2)::before {{ background: #38bdf8; }}
    .card:nth-child(3)::before {{ background: #22c55e; }}
    .card:nth-child(4)::before {{ background: #84cc16; }}
    .card:nth-child(5)::before {{ background: #14b8a6; }}
    .card:nth-child(6)::before {{ background: #059669; }}
    .card:nth-child(7)::before {{ background: var(--accent-2); }}
    .card.active:nth-child(n)::before {{ background: var(--accent); }}
    .card-label {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 850;
      letter-spacing: .04em;
    }}
    .card-count {{
      margin-top: 18px;
      color: var(--navy);
      font-size: 32px;
      font-weight: 850;
      line-height: 1;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      margin: 22px 0 12px;
    }}
    .submit-panel {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 10px;
      align-items: center;
      margin: 18px 0 6px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 8px 24px rgba(33, 53, 71, .06);
    }}
    .url-input {{
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 12px;
      color: var(--ink);
      background: #fbfdff;
      font: inherit;
      outline: none;
    }}
    .url-input:focus {{
      border-color: rgba(13, 148, 136, .62);
      box-shadow: 0 0 0 4px rgba(13, 148, 136, .10);
    }}
    .submit-button {{
      min-height: 42px;
      border: 0;
      border-radius: 7px;
      padding: 0 16px;
      color: #fff;
      background: var(--accent);
      font: inherit;
      font-size: 13px;
      font-weight: 850;
      cursor: pointer;
      white-space: nowrap;
      box-shadow: 0 10px 22px rgba(13, 148, 136, .22);
    }}
    .submit-button:hover {{ background: #0f766e; }}
    .flash {{
      margin: 10px 0 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #f0fdfa;
      color: #0f766e;
      font-size: 13px;
      font-weight: 750;
    }}
    .flash.error {{
      background: #fff1f2;
      color: #be123c;
      border-color: #fecdd3;
    }}
    .filters {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
    }}
    .filter {{
      border-radius: 6px;
      padding: 8px 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .filter.active {{
      background: var(--navy);
      color: #fff;
      box-shadow: 0 6px 16px rgba(33, 53, 71, .20);
    }}
    .match-count {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 750;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1120px;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f8fafc;
      color: var(--muted);
      font-size: 11px;
      font-weight: 850;
      letter-spacing: .05em;
      text-transform: uppercase;
      text-align: left;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }}
    td {{
      padding: 15px 14px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      font-size: 14px;
    }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tr:hover td {{ background: #f8fbfc; }}
    .title {{
      max-width: 330px;
      color: var(--navy);
      font-weight: 800;
      line-height: 1.35;
    }}
    .tiny {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .pill {{
      display: inline-block;
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 5px 8px;
      margin: 0 4px 4px 0;
      font-size: 11px;
      font-weight: 850;
      white-space: nowrap;
    }}
    .DISCOVERED, .PENDING {{ background: #fff7ed; color: #9a3412; border-color: #fed7aa; }}
    .DOWNLOADING, .PUBLISHING {{ background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }}
    .DOWNLOADED {{ background: #ecfdf5; color: #047857; border-color: #bbf7d0; }}
    .PROCESSED {{ background: #f7fee7; color: #4d7c0f; border-color: #d9f99d; }}
    .TRANSLATED, .PUBLISHED {{ background: #f0fdfa; color: #0f766e; border-color: #99f6e4; }}
    .FAILED {{ background: #fff1f2; color: #be123c; border-color: #fecdd3; }}
    .SKIPPED {{ background: #f1f5f9; color: #475569; border-color: #cbd5e1; }}
    .paths {{
      font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
      color: #334155;
      line-height: 1.5;
      overflow-wrap: anywhere;
      max-width: 330px;
    }}
    .error {{
      color: #be123c;
      font-weight: 750;
      max-width: 280px;
      line-height: 1.45;
    }}
    .empty {{
      text-align: center;
      padding: 46px 20px;
      color: var(--muted);
      font-weight: 700;
    }}
    @media (max-width: 760px) {{
      .shell {{ padding: 20px 14px 34px; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
      .identity {{ min-width: auto; }}
      .meta {{ grid-template-columns: 1fr; min-width: auto; width: 100%; }}
      .toolbar {{ align-items: flex-start; flex-direction: column; }}
      .submit-panel {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="identity">
        <div class="eyebrow">Publishing Control</div>
        <h1>CrossPost</h1>
        <div class="subtitle">本地只读仪表盘，查看采集、处理、翻译和发布进度。</div>
        <nav class="nav" aria-label="页面导航">
          {_render_nav_link("overview", "概览", model)}
          {_render_nav_link("records", "制作记录", model)}
        </nav>
      </div>
      <div class="meta">
        <div class="summary">
          <div class="summary-label">Content</div>
          <span class="metric">{model.total}</span>
          <div class="summary-note">条内容</div>
        </div>
        <div class="summary">
          <div class="summary-label">Publishing</div>
          <span class="metric">{model.publish_counts[PublishStatus.PUBLISHED]}</span>
          <div class="summary-note">成功，{model.publish_counts[PublishStatus.FAILED]} 失败</div>
        </div>
        <div class="summary">
          <div class="summary-label">Runtime</div>
          <span class="metric">{_format_dt(model.generated_at)[11:]}</span>
          <div class="summary-note">{_escape(model.database_url)}</div>
        </div>
      </div>
    </header>

    {cards_section}

    <form class="submit-panel" method="post" action="{model.base_path or ""}/submit">
      <input class="url-input" type="url" name="video_url" placeholder="粘贴 YouTube 视频 URL" required>
      <button class="submit-button" type="submit">加入处理队列</button>
    </form>
    {flash_html}

    <section class="toolbar">
      <div class="filters">
        {_render_filter("all", "ALL", model)}
        {"".join(_render_filter(s.value, s.value, model) for s in CONTENT_STATUS_ORDER)}
      </div>
      <div class="match-count">{len(model.items)} 条匹配记录</div>
    </section>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>状态</th>
            <th>视频</th>
            <th>频道</th>
            <th>时长</th>
            <th>时间</th>
            <th>处理产物</th>
            <th>发布</th>
            <th>错误</th>
          </tr>
        </thead>
        <tbody>
          {rows or empty_state}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def create_handler(
    engine: Engine,
    database_url: str,
    settings: AppSettings | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler bound to a database engine."""
    app_settings = settings or AppSettings()
    app_settings.database_url = database_url
    run_lock = threading.Lock()

    def _trigger_pipeline() -> None:
        if not run_lock.acquire(blocking=False):
            return
        try:
            poll_and_download_job(app_settings)
        finally:
            run_lock.release()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in {"/", "/index.html", "/records"}:
                self.send_error(404, "Not found")
                return

            status = parse_qs(parsed.query).get("status", ["all"])[0]
            flash = parse_qs(parsed.query).get("flash", [""])[0]
            base_path = self.headers.get("X-Script-Name", "")
            view = "records" if parsed.path == "/records" else "overview"
            model = build_dashboard_model(
                engine,
                database_url,
                status=status,
                base_path=base_path,
                flash=flash,
                view=view,
            )
            body = render_dashboard(model).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/submit":
                self.send_error(404, "Not found")
                return

            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length).decode("utf-8")
            video_url = parse_qs(body).get("video_url", [""])[0]
            base_path = self.headers.get("X-Script-Name", "")

            try:
                content, created = enqueue_video_url(engine, video_url)
                message = "已加入处理队列" if created else "视频已在队列中"
                threading.Thread(target=_trigger_pipeline, daemon=True).start()
                location = f"{base_path}/records?flash={quote(f'{message}: {content.video_id}')}"
            except ValueError as exc:
                location = f"{base_path}/records?flash={quote(f'error:{exc}')}"

            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return DashboardHandler


def serve_dashboard(
    database_url: str,
    host: str = "127.0.0.1",
    port: int = 8086,
    settings: AppSettings | None = None,
) -> None:
    """Start the local dashboard server."""
    engine = get_engine(database_url)
    init_db(engine)
    server = ThreadingHTTPServer((host, port), create_handler(engine, database_url, settings=settings))
    print(f"CrossPost dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        engine.dispose()


def main() -> None:
    """CLI entry point for the dashboard."""
    parser = argparse.ArgumentParser(description="Run the CrossPost read-only dashboard.")
    parser.add_argument("--config", default="config.yaml", help="Path to CrossPost YAML config.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8086, help="Port to bind.")
    parser.add_argument("--database-url", default=None, help="Override database URL from config.")
    args = parser.parse_args()

    settings = AppSettings(_yaml_file=args.config)
    database_url = args.database_url or settings.database_url
    settings.database_url = database_url
    serve_dashboard(database_url, host=args.host, port=args.port, settings=settings)


def _render_status_card(status: ContentStatus, model: DashboardModel) -> str:
    active = " active" if model.selected_status == status.value else ""
    return f"""
      <a class="card{active}" href="{_dashboard_href(status.value, model)}">
        <span class="card-label">{status.value}</span>
        <div class="card-count">{model.content_counts[status]}</div>
      </a>
    """


def _render_filter(value: str, label: str, model: DashboardModel) -> str:
    active = " active" if model.selected_status == value else ""
    return f'<a class="filter{active}" href="{_dashboard_href(value, model)}">{label}</a>'


def _dashboard_href(status: str, model: DashboardModel) -> str:
    base_path = model.base_path or ""
    path = "/records" if model.view == "records" else "/"
    return f"{base_path}{path}?status={status}"


def _render_nav_link(view: str, label: str, model: DashboardModel) -> str:
    active = " active" if model.view == view else ""
    base_path = model.base_path or ""
    path = "/records" if view == "records" else "/"
    return f'<a class="nav-link{active}" href="{base_path}{path}">{label}</a>'


def _render_flash(flash: str) -> str:
    if not flash:
        return ""
    is_error = flash.startswith("error:")
    message = flash[len("error:"):] if is_error else flash
    class_name = "flash error" if is_error else "flash"
    return f'<div class="{class_name}">{_escape(message)}</div>'


def _render_content_row(item: Content, records: list[PublishRecord]) -> str:
    paths = [
        ("video", item.video_path),
        ("srt", item.srt_path),
        ("zh", item.translated_srt_path),
        ("ass", item.ass_path),
        ("final", item.processed_video_path),
    ]
    paths_html = "<br>".join(
        f"<strong>{label}</strong>: {_escape(path)}" for label, path in paths if path
    )
    if not paths_html:
        paths_html = '<span class="tiny">暂无产物</span>'

    publish_html = "".join(_render_publish_record(record) for record in records)
    if not publish_html:
        publish_html = '<span class="tiny">暂无发布记录</span>'

    return f"""
      <tr>
        <td><span class="pill {item.status.value}">{item.status.value}</span></td>
        <td class="title">
          {_escape(item.title or item.video_id)}
          <span class="tiny">{_escape(item.video_url or item.video_id)}</span>
        </td>
        <td>{_escape(item.channel_id)}</td>
        <td>{_format_duration(item.duration)}</td>
        <td>
          <span class="tiny">发布 {_format_dt(item.published_at)}</span>
          <span class="tiny">发现 {_format_dt(item.discovered_at)}</span>
          <span class="tiny">下载 {_format_dt(item.downloaded_at)}</span>
          <span class="tiny">处理 {_format_dt(item.processed_at)}</span>
        </td>
        <td class="paths">{paths_html}</td>
        <td>{publish_html}</td>
        <td class="error">{_escape(item.error_message or "")}</td>
      </tr>
    """


def _render_publish_record(record: PublishRecord) -> str:
    detail = record.platform_url or record.error_message or record.next_attempt_at or ""
    return f"""
      <div>
        <span class="pill {record.status.value}">{_escape(record.platform)} {record.status.value}</span>
        <span class="tiny">尝试 {record.attempts} 次 {_escape(detail)}</span>
      </div>
    """


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "-"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    main()

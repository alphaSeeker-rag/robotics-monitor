#!/usr/bin/env python3
"""
フィジカルAI・ロボティクス監視スクリプト
各国(日米中韓)のメディア・企業ブログ・arXiv を監視し、
指定キーワードが含まれる記事を収集。
日本語以外の記事は Claude AI で日本語に翻訳・要約する。
"""

import os
import json
import re
import time
import hashlib
import logging
import argparse
import webbrowser
from datetime import datetime
from html import escape
from pathlib import Path

import feedparser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SEEN_FILE = Path("seen_articles.json")
CONFIG_FILE = Path("config.json")
REPORT_FILE = Path("report.html")
LOG_FILE = Path("articles.json")

# フィードURL -> 表示名・国/種別ラベル
SOURCE_LABELS = {
    "therobotreport.com": ("The Robot Report", "US"),
    "spectrum.ieee.org": ("IEEE Spectrum", "US"),
    "techcrunch.com": ("TechCrunch", "US"),
    "blogs.nvidia.com": ("NVIDIA Blog", "US"),
    "deepmind.google": ("Google DeepMind", "US"),
    "technologyreview.com": ("MIT Tech Review", "US"),
    "venturebeat.com": ("VentureBeat", "US"),
    "sciencedaily.com": ("ScienceDaily", "US"),
    "aiplus": ("ITmedia AI+", "JP"),
    "monoist": ("MONOist", "JP"),
    "news_bursts": ("ITmedia NEWS", "JP"),
    "pc.watch.impress": ("PC Watch", "JP"),
    "gigazine.net": ("GIGAZINE", "JP"),
    "zdnet": ("ZDNet", "JP"),
    "irobotnews.com": ("The Robot Times (韓)", "KR"),
    "zdkorea": ("ZDNet Korea", "KR"),
    "pandaily.com": ("Pandaily", "CN"),
    "technode.com": ("TechNode", "CN"),
    "36kr.com": ("36Kr", "CN"),
    "cs.RO": ("arXiv cs.RO", "arXiv"),
    "cs.AI": ("arXiv cs.AI", "arXiv"),
    "huggingface.co": ("Hugging Face", "Lab"),
    "research.google": ("Google Research", "Lab"),
    "developer.nvidia.com": ("NVIDIA Developer", "Lab"),
    "microsoft.com": ("Microsoft Research", "Lab"),
    "bair.berkeley.edu": ("Berkeley AI (BAIR)", "Lab"),
}

# 旧データ(絵文字旗)→ 新コードの変換表
FLAG_MIGRATE = {"🇺🇸": "US", "🇯🇵": "JP", "🇰🇷": "KR", "🇨🇳": "CN",
                "📄": "arXiv", "🤖": "Lab", "🔬": "Lab", "🌐": "Web"}
# 国/種別コード -> 表示色クラス(国旗が無い arXiv/Lab/Web 用)
FLAG_CLASS = {"arXiv": "fl-arxiv", "Lab": "fl-lab", "Web": "fl-web"}
# 国コード -> flag-icons の ISO コード(国旗マーク表示)
COUNTRY_ISO = {"US": "us", "JP": "jp", "KR": "kr", "CN": "cn"}

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>PHYSICAL AI REVIEW — フィジカルAI・ロボティクス監視レポート</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@400;500;600;700;900&family=Playfair+Display:ital,wght@0,500;0,700;0,900;1,500&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flag-icons@7.2.3/css/flag-icons.min.css">
<style>
  :root {{
    --bg: #f4f1ea;
    --paper: #fbfaf6;
    --ink: #1a1714;
    --ink-soft: #4a443c;
    --line: #d8d2c4;
    --accent: #9b2226;
    --accent-soft: #b8693d;
    --serif: "Noto Serif JP", "Playfair Display", Georgia, serif;
    --display: "Playfair Display", "Noto Serif JP", Georgia, serif;
    --sans: "Noto Sans JP", -apple-system, "Segoe UI", sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--serif); background: var(--bg); color: var(--ink);
          line-height: 1.6; -webkit-font-smoothing: antialiased; position: relative; }}
  /* circuit-trace vertical rails on both margins (fixed) */
  body::before, body::after {{ content: ""; position: fixed; top: 0; bottom: 0;
          width: 90px; background: url("circuit-rail.svg") repeat-y top center;
          background-size: 90px auto; opacity: 0.16; pointer-events: none; z-index: 0; }}
  body::before {{ left: 0; }}
  body::after {{ right: 0; transform: scaleX(-1); }}
  header, .filters, main, footer {{ position: relative; z-index: 1; }}

  /* ===== Masthead ===== */
  header {{ background: var(--paper); border-bottom: 3px double var(--ink);
            padding: 38px 32px 18px; position: relative; overflow: hidden; }}
  /* 3D humanoid mascots flanking the title (mirrored pair) */
  header::before, header::after {{ content: ""; position: absolute; bottom: 8px;
            width: 118px; height: 176px; pointer-events: none;
            background: url("humanoid-3d.svg") no-repeat bottom center / contain;
            filter: drop-shadow(0 6px 10px rgba(0,0,0,.12)); }}
  header::before {{ left: 3.5%; transform: scaleX(-1); }}
  header::after {{ right: 3.5%; }}
  .masthead {{ max-width: 1040px; margin: 0 auto; text-align: center; position: relative; z-index: 2; }}

  @media (max-width: 860px) {{
    /* hide side robot + left rail, but keep one small robot centered on top */
    header {{ padding-top: 150px; }}
    header::before {{ display: none; }}
    header::after {{ width: 96px; height: 134px; left: 50%; right: auto;
            top: 14px; bottom: auto; transform: translateX(-50%); }}
    body::before, body::after {{ display: none; }}
    .masthead-rule::before, .masthead-rule::after {{ width: 40px; }}
  }}
  .eyebrow {{ font-family: var(--sans); font-size: 0.66rem; font-weight: 700;
              letter-spacing: .42em; text-transform: uppercase; color: var(--accent);
              margin-bottom: 10px; }}
  header h1 {{ font-family: var(--display); font-weight: 900; font-size: 2.7rem;
               line-height: 1.05; letter-spacing: -.01em; margin-bottom: 6px; }}
  header h1 .jp {{ display: block; font-family: var(--serif); font-size: 1.05rem;
                   font-weight: 600; letter-spacing: .14em; color: var(--ink-soft);
                   margin-top: 10px; }}
  .masthead-rule {{ display: flex; align-items: center; justify-content: center; gap: 14px;
                    margin-top: 14px; font-family: var(--sans); font-size: 0.7rem;
                    letter-spacing: .18em; text-transform: uppercase; color: var(--ink-soft); }}
  .masthead-rule::before, .masthead-rule::after {{ content: ""; height: 1px; width: 70px;
                    background: var(--line); }}
  .dateline {{ margin-top: 10px; font-family: var(--sans); font-size: 0.66rem; font-weight: 700;
               letter-spacing: .16em; text-transform: uppercase; color: var(--accent); }}
  .dateline .dot {{ color: var(--line); margin: 0 8px; }}

  /* ===== Filters ===== */
  .filters {{ position: sticky; top: 0; z-index: 10; background: rgba(244,241,234,.94);
              backdrop-filter: blur(6px); border-bottom: 1px solid var(--line);
              padding: 12px 32px; display: flex; gap: 7px; flex-wrap: wrap;
              align-items: center; justify-content: center; }}
  .filters span {{ font-family: var(--sans); font-size: 0.72rem; font-weight: 700;
                   letter-spacing: .1em; text-transform: uppercase; color: var(--accent);
                   margin-right: 6px; }}
  .btn {{ font-family: var(--sans); padding: 4px 13px; border-radius: 2px;
          border: 1px solid var(--line); background: transparent; color: var(--ink-soft);
          cursor: pointer; font-size: 0.74rem; font-weight: 500; transition: all .15s; }}
  .btn:hover {{ border-color: var(--ink); color: var(--ink); }}
  .btn.active {{ background: var(--ink); color: var(--paper); border-color: var(--ink); }}

  /* ===== Layout ===== */
  main {{ max-width: 800px; margin: 40px auto 80px; padding: 0 28px; }}

  .section-label {{ font-family: var(--display); font-weight: 700; font-size: 1.5rem;
                    color: var(--ink); margin: 44px 0 6px; padding-bottom: 10px;
                    border-bottom: 2px solid var(--ink); display: flex;
                    align-items: baseline; justify-content: space-between; }}
  .section-label::after {{ font-family: var(--sans); font-size: 0.68rem; font-weight: 700;
                    letter-spacing: .12em; color: var(--accent); }}

  /* ===== Article ===== */
  .card {{ padding: 26px 0; border-bottom: 1px solid var(--line); }}
  .card:last-child {{ border-bottom: none; }}
  .card-title a {{ text-decoration: none; color: var(--ink); font-family: var(--serif);
                   font-size: 1.32rem; font-weight: 700; line-height: 1.4;
                   transition: color .15s; display: inline; background-image: linear-gradient(var(--accent), var(--accent));
                   background-size: 0% 1.5px; background-repeat: no-repeat;
                   background-position: 0 100%; transition: background-size .25s, color .15s; }}
  .card-title a:hover {{ color: var(--accent); background-size: 100% 1.5px; }}
  .card-meta {{ display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; align-items: center;
                font-family: var(--sans); }}
  .flag {{ display: inline-block; font-size: 0.68rem; font-weight: 700; letter-spacing: .06em;
           padding: 3px 9px; border-radius: 3px; color: #fff; text-transform: uppercase; }}
  .fl-arxiv {{ background: #6b21a8; }}
  .fl-lab {{ background: #4a443c; }}
  .fl-web {{ background: #9b948a; }}
  /* national flag icons */
  .flagicon {{ font-size: 1.35rem; border-radius: 2px; vertical-align: middle;
               box-shadow: 0 0 0 1px rgba(0,0,0,.18); }}
  .source {{ font-size: 0.72rem; color: var(--ink); font-weight: 700; letter-spacing: .04em; }}
  .date {{ font-size: 0.7rem; color: #9b948a; letter-spacing: .03em; }}
  .kw {{ display: inline-block; padding: 2px 8px; border: 1px solid var(--accent);
         border-radius: 2px; font-size: 0.64rem; font-weight: 700; letter-spacing: .03em;
         color: var(--accent); text-transform: uppercase; }}

  /* ===== AI summary (editorial sidebar) ===== */
  .ai-box {{ margin-top: 18px; background: var(--paper); border: 1px solid var(--line);
             border-left: 4px solid var(--accent); padding: 18px 22px; position: relative; }}
  .ai-label {{ font-family: var(--sans); font-size: 0.62rem; font-weight: 700; color: var(--accent);
               text-transform: uppercase; letter-spacing: .18em; margin-bottom: 10px; }}
  .ai-title-ja {{ font-family: var(--serif); font-size: 1.12rem; font-weight: 700;
                  color: var(--ink); margin-bottom: 10px; line-height: 1.45; }}
  .ai-summary {{ font-family: var(--serif); font-size: 0.92rem; color: var(--ink-soft);
                 line-height: 1.85; margin-bottom: 12px; }}
  .ai-insights {{ list-style: none; padding-left: 0; margin-top: 4px;
                  border-top: 1px solid var(--line); padding-top: 12px; }}
  .ai-insights li {{ font-family: var(--sans); font-size: 0.84rem; color: var(--ink);
                     line-height: 1.65; margin-bottom: 8px; padding-left: 22px; position: relative; }}
  .ai-insights li::before {{ content: "→"; position: absolute; left: 0; top: 0;
                     color: var(--accent); font-weight: 700; }}

  .empty {{ text-align: center; color: var(--ink-soft); padding: 80px 0;
            font-family: var(--serif); font-size: 1.1rem; }}

  footer {{ text-align: center; padding: 40px 20px; border-top: 3px double var(--ink);
            font-family: var(--sans); font-size: 0.68rem; letter-spacing: .14em;
            text-transform: uppercase; color: var(--ink-soft); }}

  @media (max-width: 640px) {{
    header h1 {{ font-size: 1.8rem; }}
    .card-title a {{ font-size: 1.15rem; }}
    main {{ padding: 0 18px; }}
  }}
</style>
</head>
<body>
<header>
  <div class="masthead">
    <div class="eyebrow">Daily Intelligence Briefing</div>
    <h1>Physical AI Review
      <span class="jp">フィジカルAI・ロボティクス監視レポート</span>
    </h1>
    <div class="masthead-rule">日米中韓メディア · 企業ブログ · arXiv</div>
    <div class="dateline">{total} Articles<span class="dot">●</span>Updated {updated}</div>
  </div>
</header>
<div class="filters">
  <span>絞り込み</span>
  <button class="btn active" onclick="filter(this,'')">すべて</button>
  {kw_buttons}
</div>
<main id="main">
{cards}
</main>
<footer>
  更新 {updated} ／ 全 {total} 件 ／ 2分ごとに自動更新
</footer>
<script>
  function filter(btn, kw) {{
    document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.card').forEach(c => {{
      c.style.display = (!kw || c.dataset.kw.includes(kw)) ? '' : 'none';
    }});
    document.querySelectorAll('.section-label').forEach(s => {{
      let n = s.nextElementSibling, vis = 0;
      while (n && n.classList.contains('card')) {{
        if (n.style.display !== 'none') vis++;
        n = n.nextElementSibling;
      }}
      s.style.display = vis ? '' : 'none';
    }});
  }}
</script>
</body>
</html>
"""


def load_config() -> dict:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def load_seen() -> set:
    if SEEN_FILE.exists():
        with SEEN_FILE.open(encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set) -> None:
    with SEEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(list(seen), f)


def load_log() -> list:
    if LOG_FILE.exists():
        with LOG_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(articles: list) -> None:
    with LOG_FILE.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def article_id(entry) -> str:
    key = getattr(entry, "id", None) or getattr(entry, "link", "") or entry.title
    return hashlib.sha1(key.encode()).hexdigest()


def matches_keywords(entry, keywords: list) -> list:
    text = " ".join([
        getattr(entry, "title", ""),
        getattr(entry, "summary", ""),
    ]).lower()
    return [kw for kw in keywords if kw.lower() in text]


def source_label(url: str, feed_title: str) -> tuple:
    for key, (name, flag) in SOURCE_LABELS.items():
        if key in url:
            return name, flag
    return (feed_title or url)[:30], "Web"


def needs_translation(text: str) -> bool:
    """日本語(ひらがな・カタカナ)を含まない記事は翻訳対象(英・中・韓)"""
    if not text:
        return False
    for c in text:
        if "぀" <= c <= "ヿ":  # ひらがな + カタカナ
            return False
    return True


def get_anthropic_client(config: dict):
    api_key = config.get("anthropic_api_key", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        log.warning("anthropic 未インストール: pip install anthropic")
        return None


def ai_summarize(title: str, body: str, client, model: str):
    content = f"Title: {title}"
    if body:
        clean = re.sub(r"<[^>]+>", "", body)
        content += f"\n\nExcerpt: {clean[:900]}"
    prompt = (
        "あなたはロボティクス・フィジカルAIの専門アナリストです。"
        "以下の記事(英語/中国語/韓国語)を日本語に翻訳・要約し、重要インサイトを抽出してください。\n\n"
        f"{content}\n\n"
        "次のJSON形式のみで回答(前後に余分なテキスト不要):\n"
        '{"title_ja": "日本語タイトル", "summary": "3文以内の日本語要約", '
        '"insights": ["技術的・産業的インサイト1", "インサイト2", "インサイト3"]}'
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if hasattr(b, "text")), "")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        log.debug("AI要約エラー: %s", e)
    return None


def build_report(articles: list, keywords: list) -> None:
    if not articles:
        cards_html = '<p class="empty">まだ記事がありません。次回の自動収集をお待ちください。</p>'
        kw_buttons = ""
    else:
        # ヒット件数の多いキーワードだけボタン化(上位30)
        kw_count = {}
        for a in articles:
            for k in a.get("keywords", []):
                kw_count[k] = kw_count.get(k, 0) + 1
        top_kws = sorted(kw_count, key=lambda k: kw_count[k], reverse=True)[:30]
        kw_buttons = " ".join(
            f'<button class="btn" onclick="filter(this,\'{escape(k)}\')">{escape(k)} ({kw_count[k]})</button>'
            for k in top_kws
        )

        grouped = {}
        for a in articles:
            day = a.get("detected_at", "")[:10] or "不明"
            grouped.setdefault(day, []).append(a)

        sections = []
        for day in sorted(grouped.keys(), reverse=True):
            sections.append(f'<div class="section-label">{escape(day)}　({len(grouped[day])}件)</div>')
            for a in grouped[day]:
                kws_data = "|".join(a.get("keywords", []))
                kws_html = " ".join(f'<span class="kw">{escape(k)}</span>' for k in a.get("keywords", []))
                ai = a.get("ai_summary")
                if ai:
                    insights = "".join(f"<li>{escape(i)}</li>" for i in ai.get("insights", []))
                    ai_block = (
                        '<div class="ai-box">'
                        '<div class="ai-label">AI 日本語要約・インサイト</div>'
                        f'<div class="ai-title-ja">{escape(ai.get("title_ja",""))}</div>'
                        f'<p class="ai-summary">{escape(ai.get("summary",""))}</p>'
                        f'<ul class="ai-insights">{insights}</ul>'
                        "</div>"
                    )
                else:
                    ai_block = ""
                flag = a.get("flag", "Web")
                flag = FLAG_MIGRATE.get(flag, flag)
                iso = COUNTRY_ISO.get(flag)
                if iso:
                    flag_html = f'<span class="fi fi-{iso} flagicon" title="{escape(flag)}"></span>'
                else:
                    flag_cls = FLAG_CLASS.get(flag, "fl-web")
                    flag_html = f'<span class="flag {flag_cls}">{escape(flag)}</span>'
                sections.append(
                    f'<div class="card" data-kw="{escape(kws_data)}">'
                    f'<div class="card-title"><a href="{escape(a["link"])}" target="_blank">{escape(a["title"])}</a></div>'
                    f'<div class="card-meta">{kws_html}'
                    f'{flag_html}'
                    f'<span class="source">{escape(a["source"])}</span>'
                    f'<span class="date">{escape(a.get("published",""))}</span>'
                    f'</div>{ai_block}</div>'
                )
        cards_html = "\n".join(sections)

    html = HTML_TEMPLATE.format(
        updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total=len(articles),
        kw_buttons=kw_buttons,
        cards=cards_html,
    )
    REPORT_FILE.write_text(html, encoding="utf-8")


def check_feed(url: str, keywords: list, seen: set, config: dict,
               ai_client, summary_budget: list) -> list:
    found = []
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0 robotics-monitor/1.0"})
        name, flag = source_label(url, feed.feed.get("title", ""))
        model = config.get("summary_model", "claude-opus-4-7")
        for entry in feed.entries:
            aid = article_id(entry)
            if aid in seen:
                continue
            seen.add(aid)
            hit = matches_keywords(entry, keywords)
            if not hit:
                continue

            title = getattr(entry, "title", "(無題)")
            body = getattr(entry, "summary", "")
            article = {
                "title": title,
                "link": getattr(entry, "link", ""),
                "published": getattr(entry, "published", ""),
                "keywords": hit,
                "source": name,
                "flag": flag,
                "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ai_summary": None,
            }

            if (ai_client and config.get("summarize_foreign")
                    and needs_translation(title) and summary_budget[0] > 0):
                log.info("AI要約中(%s): %s", name, title[:55])
                ai = ai_summarize(title, body, ai_client, model)
                if ai:
                    article["ai_summary"] = ai
                    summary_budget[0] -= 1

            found.append(article)
            log.info("【ヒット】%s %s | %s", flag, title[:60], ", ".join(hit))
    except Exception as e:
        log.warning("フィード取得エラー (%s): %s", url, e)
    return found


def run_once(config: dict) -> int:
    keywords = config["keywords"]
    ai_client = get_anthropic_client(config)
    if ai_client:
        log.info("AI要約: 有効 (model=%s, 上限=%d件/回)",
                 config.get("summary_model"), config.get("max_ai_summaries_per_run", 15))
    elif config.get("summarize_foreign"):
        log.info("AI要約: 無効 (anthropic_api_key 未設定)")

    summary_budget = [config.get("max_ai_summaries_per_run", 15)]
    seen = load_seen()
    all_articles = load_log()

    new_articles = []
    for url in config["feeds"]:
        new_articles.extend(check_feed(url, keywords, seen, config, ai_client, summary_budget))

    if new_articles:
        all_articles = new_articles + all_articles
        save_log(all_articles)
    build_report(all_articles, keywords)
    save_seen(seen)
    log.info("%d件の新着 / 累計%d件 → report.html を更新", len(new_articles), len(all_articles))
    return len(new_articles)


def main():
    parser = argparse.ArgumentParser(description="フィジカルAI・ロボティクス監視")
    parser.add_argument("--once", action="store_true", help="1回だけ実行")
    parser.add_argument("--report", action="store_true", help="レポートを開くだけ")
    args = parser.parse_args()

    config = load_config()

    if args.report:
        build_report(load_log(), config["keywords"])
        webbrowser.open(REPORT_FILE.resolve().as_uri())
        return

    if args.once:
        run_once(config)
        webbrowser.open(REPORT_FILE.resolve().as_uri())
    else:
        interval = config.get("interval_seconds", 600)
        first = True
        while True:
            run_once(config)
            if first:
                webbrowser.open(REPORT_FILE.resolve().as_uri())
                first = False
            log.info("%d秒後に次回チェック...", interval)
            time.sleep(interval)


if __name__ == "__main__":
    main()

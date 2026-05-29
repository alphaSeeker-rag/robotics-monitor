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

# フィードURL -> 表示名・国ラベル
SOURCE_LABELS = {
    "therobotreport.com": ("The Robot Report", "🇺🇸"),
    "spectrum.ieee.org": ("IEEE Spectrum", "🇺🇸"),
    "techcrunch.com": ("TechCrunch", "🇺🇸"),
    "blogs.nvidia.com": ("NVIDIA Blog", "🇺🇸"),
    "deepmind.google": ("Google DeepMind", "🇺🇸"),
    "technologyreview.com": ("MIT Tech Review", "🇺🇸"),
    "venturebeat.com": ("VentureBeat", "🇺🇸"),
    "sciencedaily.com": ("ScienceDaily", "🇺🇸"),
    "aiplus": ("ITmedia AI+", "🇯🇵"),
    "monoist": ("MONOist", "🇯🇵"),
    "news_bursts": ("ITmedia NEWS", "🇯🇵"),
    "pc.watch.impress": ("PC Watch", "🇯🇵"),
    "gigazine.net": ("GIGAZINE", "🇯🇵"),
    "zdnet": ("ZDNet", "🇯🇵"),
    "irobotnews.com": ("The Robot Times (韓)", "🇰🇷"),
    "zdkorea": ("ZDNet Korea", "🇰🇷"),
    "pandaily.com": ("Pandaily", "🇨🇳"),
    "technode.com": ("TechNode", "🇨🇳"),
    "36kr.com": ("36Kr", "🇨🇳"),
    "cs.RO": ("arXiv cs.RO", "📄"),
    "cs.AI": ("arXiv cs.AI", "📄"),
    "huggingface.co": ("Hugging Face", "🤖"),
    "research.google": ("Google Research", "🔬"),
    "developer.nvidia.com": ("NVIDIA Developer", "🔬"),
    "microsoft.com": ("Microsoft Research", "🔬"),
    "bair.berkeley.edu": ("Berkeley AI (BAIR)", "🔬"),
}

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="120">
<title>フィジカルAI・ロボティクス監視レポート</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
          background: #0f1117; color: #e8eaed; }}
  header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff;
            padding: 22px 32px; border-bottom: 2px solid #2a4d8f; }}
  header h1 {{ font-size: 1.35rem; font-weight: 700; letter-spacing: .02em; }}
  header .meta {{ font-size: 0.8rem; color: #8ab; margin-top: 4px; }}
  .filters {{ background: #161922; border-bottom: 1px solid #262b38;
              padding: 12px 32px; display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }}
  .filters span {{ font-size: 0.8rem; color: #8a90a0; margin-right: 4px; }}
  .btn {{ padding: 5px 13px; border-radius: 20px; border: 1px solid #333a4a;
          background: #1c2030; color: #cdd2dc; cursor: pointer; font-size: 0.8rem; transition: all .15s; }}
  .btn:hover, .btn.active {{ background: #2a4d8f; color: #fff; border-color: #3a6ad0; }}
  main {{ max-width: 980px; margin: 24px auto; padding: 0 16px; }}
  .card {{ background: #161922; border: 1px solid #232838; border-radius: 12px; padding: 18px 22px;
           margin-bottom: 12px; transition: border-color .15s; }}
  .card:hover {{ border-color: #2a4d8f; }}
  .card-title a {{ text-decoration: none; color: #e8eaed; font-size: 1.02rem;
                   font-weight: 600; line-height: 1.55; }}
  .card-title a:hover {{ color: #6da8ff; }}
  .card-meta {{ display: flex; gap: 10px; margin-top: 9px; flex-wrap: wrap; align-items: center; }}
  .source {{ font-size: 0.76rem; color: #7a90b8; font-weight: 600; }}
  .date {{ font-size: 0.74rem; color: #5a6070; }}
  .kw {{ display: inline-block; padding: 2px 9px; border-radius: 11px;
         font-size: 0.7rem; font-weight: 600; background: #1e2c50; color: #7fa8ff; }}
  .ai-box {{ margin-top: 14px; background: #131a26; border-left: 3px solid #3a6ad0;
             border-radius: 0 8px 8px 0; padding: 12px 16px; }}
  .ai-label {{ font-size: 0.68rem; font-weight: 700; color: #5b9bff;
               text-transform: uppercase; letter-spacing: .08em; margin-bottom: 7px; }}
  .ai-title-ja {{ font-size: 0.96rem; font-weight: 600; color: #dfe8ff; margin-bottom: 8px; line-height: 1.5; }}
  .ai-summary {{ font-size: 0.85rem; color: #b8c0d0; line-height: 1.7; margin-bottom: 8px; }}
  .ai-insights {{ padding-left: 18px; margin-top: 4px; }}
  .ai-insights li {{ font-size: 0.83rem; color: #aab4c8; line-height: 1.6; margin-bottom: 3px; }}
  .empty {{ text-align: center; color: #5a6070; padding: 60px 0; font-size: 1rem; }}
  .section-label {{ font-size: 0.76rem; font-weight: 700; color: #6a7390;
                    text-transform: uppercase; letter-spacing: .06em;
                    margin: 26px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #232838; }}
</style>
</head>
<body>
<header>
  <h1>🤖 フィジカルAI・ロボティクス監視レポート</h1>
  <div class="meta">更新: {updated} ／ 全 {total} 件 ／ 日米中韓メディア + 企業ブログ + arXiv ／ 2分ごとに自動更新</div>
</header>
<div class="filters">
  <span>絞り込み:</span>
  <button class="btn active" onclick="filter(this,'')">すべて</button>
  {kw_buttons}
</div>
<main id="main">
{cards}
</main>
<script>
  function filter(btn, kw) {{
    document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.card').forEach(c => {{
      c.style.display = (!kw || c.dataset.kw.includes(kw)) ? '' : 'none';
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
    return (feed_title or url)[:30], "🌐"


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
                flag = a.get("flag", "🌐")
                sections.append(
                    f'<div class="card" data-kw="{escape(kws_data)}">'
                    f'<div class="card-title"><a href="{escape(a["link"])}" target="_blank">{escape(a["title"])}</a></div>'
                    f'<div class="card-meta">{kws_html}'
                    f'<span class="source">{flag} {escape(a["source"])}</span>'
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

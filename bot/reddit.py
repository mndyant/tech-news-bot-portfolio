"""Reddit の RSS フィードから投稿を取得する

Reddit公式APIキーは不要。各subredditのRSSエンドポイント
(https://www.reddit.com/r/{subreddit}/{sort}/.rss) を利用する。
"""

import logging
from typing import List, Dict

import feedparser

log = logging.getLogger(__name__)

REDDIT_BASE_URL = "https://www.reddit.com"


def fetch_reddit(cfg: dict) -> List[Dict[str, str]]:
    """Reddit の複数subredditから投稿を取得する

    Args:
        cfg: config.jsonのreddit設定
             - subreddits: 対象subredditのリスト（例: ["MachineLearning", "LocalLLaMA"]）
             - sort: ソート方法 (hot/top/new)
             - max_results: subredditごとの取得上限数

    Returns:
        投稿情報の辞書リスト
    """
    subreddits = cfg.get("subreddits", [])
    sort = cfg.get("sort", "hot")
    max_results = cfg.get("max_results", 10)

    results = []
    for subreddit in subreddits:
        url = f"{REDDIT_BASE_URL}/r/{subreddit}/{sort}/.rss?limit={max_results}"
        log.info("Fetching Reddit r/%s: %s", subreddit, url)

        # Redditはデフォルトのfeedparser UAをブロック/空応答することがあるため明示的に指定
        feed = feedparser.parse(url, request_headers={"User-Agent": "tech-news-bot/1.0"})
        if feed.bozo and not feed.entries:
            log.error("Reddit fetch failed (r/%s): %s", subreddit, feed.bozo_exception)
            continue

        for e in feed.entries[:max_results]:
            entry_id = e.get("id") or e.get("link", "")
            results.append({
                "id": entry_id,
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "subreddit": subreddit,
            })

    log.info("Reddit: %d posts found", len(results))
    return results


def format_reddit_message(entry: Dict[str, str], title_ja: str = "") -> str:
    """Discord通知用のメッセージをフォーマットする"""
    title_part = f"**[Reddit]** r/{entry['subreddit']}: {entry['title']}"
    if title_ja:
        title_part += f"（{title_ja}）"

    lines = [title_part, entry["link"]]
    return "\n".join(lines)

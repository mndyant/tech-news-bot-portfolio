"""Redditモジュールのテスト"""

import unittest
from unittest.mock import patch, MagicMock

from bot.reddit import fetch_reddit, format_reddit_message


def make_fake_entry(entry_id, title, link):
    entry = MagicMock()
    entry.get = lambda key, default=None: {
        "id": entry_id, "title": title, "link": link,
    }.get(key, default)
    return entry


class TestFetchReddit(unittest.TestCase):
    @patch("bot.reddit.feedparser.parse")
    def test_fetch_multiple_subreddits(self, mock_parse):
        """複数subredditから投稿を集約する"""
        def side_effect(url, **kwargs):
            feed = MagicMock()
            feed.bozo = False
            if "MachineLearning" in url:
                feed.entries = [make_fake_entry("id1", "ML news", "https://reddit.com/1")]
            else:
                feed.entries = [make_fake_entry("id2", "LLaMA news", "https://reddit.com/2")]
            return feed
        mock_parse.side_effect = side_effect

        cfg = {"subreddits": ["MachineLearning", "LocalLLaMA"], "sort": "hot", "max_results": 10}
        results = fetch_reddit(cfg)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["subreddit"], "MachineLearning")
        self.assertEqual(results[1]["subreddit"], "LocalLLaMA")

    @patch("bot.reddit.feedparser.parse")
    def test_fetch_sends_user_agent(self, mock_parse):
        """RedditにブロックされないようUser-Agentを送信する"""
        feed = MagicMock()
        feed.bozo = False
        feed.entries = []
        mock_parse.return_value = feed

        cfg = {"subreddits": ["MachineLearning"], "sort": "hot", "max_results": 10}
        fetch_reddit(cfg)

        _, kwargs = mock_parse.call_args
        self.assertIn("request_headers", kwargs)
        self.assertIn("User-Agent", kwargs["request_headers"])

    @patch("bot.reddit.feedparser.parse")
    def test_fetch_failure_skips_subreddit(self, mock_parse):
        """1つのsubredditが失敗しても他は継続取得する"""
        def side_effect(url, **kwargs):
            feed = MagicMock()
            if "MachineLearning" in url:
                feed.bozo = True
                feed.bozo_exception = Exception("parse error")
                feed.entries = []
            else:
                feed.bozo = False
                feed.entries = [make_fake_entry("id2", "OK", "https://reddit.com/2")]
            return feed
        mock_parse.side_effect = side_effect

        cfg = {"subreddits": ["MachineLearning", "LocalLLaMA"], "sort": "hot", "max_results": 10}
        results = fetch_reddit(cfg)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subreddit"], "LocalLLaMA")

    @patch("bot.reddit.feedparser.parse")
    def test_max_results_per_subreddit(self, mock_parse):
        """subredditごとのmax_results制限"""
        feed = MagicMock()
        feed.bozo = False
        feed.entries = [make_fake_entry(f"id{i}", f"title{i}", f"link{i}") for i in range(5)]
        mock_parse.return_value = feed

        cfg = {"subreddits": ["MachineLearning"], "sort": "hot", "max_results": 2}
        results = fetch_reddit(cfg)

        self.assertEqual(len(results), 2)

    def test_empty_subreddits(self):
        """subredditが空の場合は空リスト"""
        results = fetch_reddit({"subreddits": []})
        self.assertEqual(results, [])


class TestFormatRedditMessage(unittest.TestCase):
    def test_without_translation(self):
        entry = {"id": "id1", "title": "ML news", "link": "https://reddit.com/1", "subreddit": "MachineLearning"}
        msg = format_reddit_message(entry)

        self.assertIn("**[Reddit]**", msg)
        self.assertIn("r/MachineLearning", msg)
        self.assertIn("ML news", msg)
        self.assertIn("https://reddit.com/1", msg)
        self.assertNotIn("（", msg)

    def test_with_translation(self):
        entry = {"id": "id1", "title": "ML news", "link": "https://reddit.com/1", "subreddit": "MachineLearning"}
        msg = format_reddit_message(entry, "MLニュース")

        self.assertIn("（MLニュース）", msg)


if __name__ == "__main__":
    unittest.main()

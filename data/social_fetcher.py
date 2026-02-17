"""Reddit social data fetcher using PRAW."""

import praw
from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT


def _get_reddit():
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


# Mapping of assets to relevant subreddits
SUBREDDIT_MAP = {
    "stock": ["wallstreetbets", "stocks", "investing"],
    "crypto": ["cryptocurrency", "bitcoin", "ethtrader"],
}


def fetch_reddit_posts(symbol: str, asset_type: str = "stock",
                       limit: int = 20) -> list[dict]:
    """Fetch recent Reddit posts mentioning a symbol.

    Args:
        symbol: Asset symbol (e.g., 'AAPL' or 'BTC')
        asset_type: 'stock' or 'crypto'
        limit: Max posts to fetch per subreddit

    Returns:
        List of dicts with title, text, score, subreddit, created.
    """
    reddit = _get_reddit()
    if reddit is None:
        return []

    ticker = symbol.split("/")[0]
    subreddits = SUBREDDIT_MAP.get(asset_type, SUBREDDIT_MAP["stock"])
    posts = []

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.search(ticker, sort="new", time_filter="week", limit=limit):
                posts.append({
                    "title": post.title,
                    "text": post.selftext[:500] if post.selftext else "",
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "subreddit": sub_name,
                    "created": post.created_utc,
                    "url": f"https://reddit.com{post.permalink}",
                })
        except Exception:
            continue

    # Sort by score (engagement)
    posts.sort(key=lambda x: x["score"], reverse=True)
    return posts


def fetch_reddit_comments(symbol: str, asset_type: str = "stock",
                          limit: int = 50) -> list[str]:
    """Fetch recent Reddit comments mentioning a symbol.

    Returns a list of comment text strings for sentiment analysis.
    """
    reddit = _get_reddit()
    if reddit is None:
        return []

    ticker = symbol.split("/")[0]
    subreddits = SUBREDDIT_MAP.get(asset_type, SUBREDDIT_MAP["stock"])
    comments = []

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.search(ticker, sort="new", time_filter="week", limit=5):
                post.comments.replace_more(limit=0)
                for comment in post.comments[:10]:
                    if hasattr(comment, "body") and len(comment.body) > 20:
                        comments.append(comment.body[:300])
                    if len(comments) >= limit:
                        break
        except Exception:
            continue

    return comments[:limit]

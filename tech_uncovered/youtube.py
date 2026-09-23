"""Only live network boundary. Official YouTube Data API; no scraping."""
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .settings import utcnow


class YouTubeError(RuntimeError):
    pass


class BudgetExceeded(YouTubeError):
    pass


@dataclass
class Usage:
    cache_hits: int = 0
    cache_misses: int = 0
    requests: int = 0
    search_requests: int = 0

    def to_dict(self):
        total = self.cache_hits + self.cache_misses
        return {**asdict(self), "quota_units_estimated_used": self.requests-self.search_requests,
                "search_quota_units_estimated_used": self.search_requests,
                "cache_hit_rate": self.cache_hits / total if total else 0.0}


def http_transport(endpoint, params, api_key):
    # Never log the URL: credentials are a query parameter.
    url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urlencode({**params, "key": api_key})
    request = Request(url, headers={"User-Agent": "TechUncovered-Radar/0.1"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def duration_seconds(value):
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", value or "")
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (float(x or 0) for x in match.groups())
    return int(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def number(value):
    return int(value) if value is not None else None


class YouTubeClient:
    def __init__(self, api_key, db, settings, refresh=False, transport=http_transport,
                 clock=utcnow, sleep=time.sleep):
        self.api_key, self.db, self.settings = api_key, db, settings
        self.refresh, self.transport, self.clock, self.sleep = refresh, transport, clock, sleep
        self.usage = Usage()

    def get(self, endpoint, params, ttl):
        key = json.dumps([endpoint, params], sort_keys=True)
        now = self.clock()
        cached = None if self.refresh else self.db.cached(key, now)
        if cached:
            self.usage.cache_hits += 1
            return cached
        self.usage.cache_misses += 1
        for attempt in range(3):
            if self.usage.requests >= self.settings.request_budget:
                raise BudgetExceeded("Per-run request budget exhausted")
            self.usage.requests += 1  # Conservative attempted-request accounting.
            if endpoint == "search":self.usage.search_requests += 1
            try:
                payload = self.transport(endpoint, params, self.api_key)
                if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                    raise YouTubeError("Malformed API response")
                fetched = self.clock()
                self.db.cache(key, payload, fetched, ttl)
                return payload, fetched.isoformat()
            except HTTPError as exc:
                reason = "http_error"
                try:
                    reason = json.loads(exc.read()).get("error", {}).get("errors", [{}])[0].get("reason", reason)
                except (ValueError, IndexError, AttributeError):
                    pass
                if reason in {"quotaExceeded", "dailyLimitExceeded"}:
                    raise BudgetExceeded("YouTube quota exhausted") from None
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise YouTubeError(f"YouTube API HTTP {exc.code} ({reason})") from None
            except (URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise YouTubeError("YouTube network request failed after retries") from None
            except (ValueError, KeyError, TypeError):
                raise YouTubeError("Invalid YouTube response") from None
            self.sleep(2 ** attempt)
        raise YouTubeError("Request failed")

    def resolve_channel(self, config):
        params = {"part": "snippet,contentDetails"}
        if config.get("channel_id"):
            params["id"] = config["channel_id"]
        else:
            params["forHandle"] = config["handle"]
        payload, observed = self.get("channels", params, timedelta(days=self.settings.channel_cache_days))
        if len(payload["items"]) != 1:
            raise YouTubeError("Channel could not be resolved uniquely; verify its handle")
        item = payload["items"][0]
        return {"channel_id": item["id"], "name": item["snippet"]["title"],
                "handle": config.get("handle"),
                "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
                "observed_at": observed}

    def uploads(self, channel):
        limit=channel.get("max_uploads",self.settings.max_uploads)
        ids, token = [], None
        while len(ids) < limit:
            params = {"part": "contentDetails", "playlistId": channel["uploads_playlist_id"],
                      "maxResults": min(50, limit - len(ids))}
            if token:
                params["pageToken"] = token
            payload, _ = self.get("playlistItems", params, timedelta(hours=self.settings.cache_hours))
            ids.extend(item["contentDetails"]["videoId"] for item in payload["items"])
            next_token = payload.get("nextPageToken")
            if not next_token:
                return list(dict.fromkeys(ids)), False
            if next_token == token:
                raise YouTubeError("Repeated pagination token")
            token = next_token
        return list(dict.fromkeys(ids)), bool(token)

    def videos(self, ids):
        payload, observed = self.get("videos", {"part": "snippet,statistics,contentDetails,liveStreamingDetails",
                                               "id": ",".join(sorted(ids))},
                                     timedelta(hours=self.settings.cache_hours))
        result = []
        for item in payload["items"]:
            snippet, stats = item["snippet"], item.get("statistics", {})
            result.append({"video_id": item["id"], "channel_id": snippet["channelId"],
                           "channel": snippet["channelTitle"], "title": snippet["title"],
                           "published_at": snippet["publishedAt"], "views": number(stats.get("viewCount")),
                           "likes": number(stats.get("likeCount")), "comments": number(stats.get("commentCount")),
                           "duration_seconds": duration_seconds(item.get("contentDetails", {}).get("duration")),
                           "url": "https://www.youtube.com/watch?v=" + item["id"], "observed_at": observed,
                           "available": True, "is_live": bool(item.get("liveStreamingDetails")) or
                           snippet.get("liveBroadcastContent", "none") != "none"})
        return result

"""Replace TopicClassifier with another implementation without changing research."""
import re
import json
from hashlib import sha256
from statistics import median
from typing import Protocol


class TopicClassifier(Protocol):
    name: str
    version: str

    def classify(self, video: dict) -> list[str]:
        """Return additive theme labels; never mutate the input video."""
        ...


class DictionaryTopicClassifier:
    name = "dictionary"
    version = "1"

    def __init__(self, themes):
        self.config_hash = sha256(json.dumps(themes, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.patterns = {
            label: [re.compile(r"(?<!\w)" + re.escape(term) + r"(?![a-z])", re.I)
                    for term in terms]
            for label, terms in themes.items()
        }

    def classify(self, video):
        return sorted(label for label, patterns in self.patterns.items()
                      if any(p.search(video["title"]) for p in patterns))


def group_topics(rows, classifier: TopicClassifier):
    top = sorted((r for r in rows if r["is_outlier"]), key=lambda r: r["rank"])[:30]
    groups = {}
    for row in top:
        for label in set(classifier.classify(row)):
            groups.setdefault(label, []).append(row)
    result = []
    for label, members in groups.items():
        if len(members) < 2:
            continue
        result.append({"theme": label, "video_count": len(members),
                       "channels": sorted({r["channel"] for r in members}),
                       "median_score": median(r["velocity_adjusted_score"] for r in members),
                       "evidence": [{"video_id": r["video_id"], "url": r["url"],
                                     "channel": r["channel"]} for r in members]})
    return sorted(result, key=lambda t: (-len(t["channels"]), -t["video_count"], -t["median_score"], t["theme"]))

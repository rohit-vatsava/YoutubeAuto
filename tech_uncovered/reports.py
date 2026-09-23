import csv
import io
import json
import os
import tempfile
from pathlib import Path


CSV_FIELDS = ["rank", "video_id", "title", "channel_id", "channel", "published_at", "observed_at",
              "views", "likes", "comments", "duration_seconds", "url", "cohort", "age_days",
              "views_per_day", "channel_median_views", "outlier_ratio", "velocity_ratio",
              "velocity_adjusted_score", "percentile", "baseline_sample_size", "baseline_median_views",
              "baseline_median_views_per_day", "eligibility_reason", "provisional", "is_outlier", "market_cohort", "source_role"]


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".radar-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def export(result, directory):
    directory = Path(directory)
    atomic_write(directory / "outliers.json", json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in result["videos"]:
        safe = dict(row)
        # Defend spreadsheet imports from formula injection in public titles/names.
        for key, value in safe.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                safe[key] = "'" + value
        writer.writerow(safe)
    atomic_write(directory / "outliers.csv", stream.getvalue())
    meta = result["metadata"]
    lines = ["# Tech Uncovered — Radar topic evidence", "",
             f"Run: {result['run_id']} | Generated: {result['generated_at']} | Mode: {meta['mode']}", "",
             "Radar-derived themes and scores, not YouTube metrics. Associations do not establish causes.",
             "Duration-based short candidates are not verified Shorts. Lifetime views/day is not current momentum.", ""]
    if meta["mode"] == "synthetic":
        lines += ["**SYNTHETIC DEMONSTRATION — no real channel performance claims.**", ""]
    if meta["partial_failures"]:
        lines += ["**Partial run:** " + "; ".join(meta["partial_failures"]), ""]
    if not result["topics"]:
        lines += ["Insufficient evidence for recurring themes among qualifying outliers.", ""]
    for topic in result["topics"]:
        lines += [f"## {topic['theme']}", "",
                  f"Evidence: {topic['video_count']} videos across {len(topic['channels'])} channel(s); "
                  f"median adjusted score {topic['median_score']:.2f}.", "",
                  "Channels: " + ", ".join(topic["channels"]) + ".", ""]
        for evidence in topic["evidence"]:
            lines.append(f"- [{evidence['channel']} / {evidence['video_id']}]({evidence['url']})")
        lines.append("")
    if meta["warnings"]:
        lines += ["## Data notes", ""] + ["- " + w for w in meta["warnings"]]
    atomic_write(directory / "top_topics.md", "\n".join(lines) + "\n")


def summary(result):
    meta = result["metadata"]
    lines = [f"Radar | {meta['mode']} | {meta['status']}",
             f"Channels processed: {meta['channels_processed']} | Videos processed: {meta['videos_processed']}",
             "Top 10 outliers:"]
    for row in result["outliers"][:10]:
        lines.append(f"  {row['velocity_adjusted_score']:.2f} | {row['channel']} | {row['title']}")
    if not result["outliers"]:
        lines.append("  None met the thresholds.")
    lines.append("Strongest recurring topics:")
    lines.extend(f"  {t['theme']}: {t['video_count']} videos / {len(t['channels'])} channels"
                 for t in result["topics"][:5])
    if not result["topics"]:
        lines.append("  Insufficient recurring evidence.")
    usage = meta["usage"]
    lines += [f"Quota units estimated used: {usage['quota_units_estimated_used']} "
              f"({usage['requests']} API attempts; actual account usage is available in Google Cloud)",
              f"Cache hit rate: {usage['cache_hit_rate']:.1%} "
              f"({usage['cache_hits']} hits / {usage['cache_hits'] + usage['cache_misses']} lookups)",
              "Partial failures: " + ("; ".join(meta["partial_failures"]) or "none")]
    lines.extend("Note: " + w for w in meta["warnings"])
    return "\n".join(lines)

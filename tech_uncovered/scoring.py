"""Independent implementation inspired by Jakeschincariol/youtube-agent-skill.
Own-channel median normalization is adapted as an idea, not copied source.
Scores are Radar heuristics, not YouTube metrics or causal predictions.
"""
from collections import defaultdict
from math import sqrt
from statistics import median

from .settings import parse_time


def cohort(duration):
    if duration is None or duration <= 0:
        return None
    return "short_candidate" if duration <= 180 else "longer_video"


def score_videos(videos, settings):
    rows = []
    groups = defaultdict(list)
    for video in videos:
        row = dict(video)
        age = (parse_time(row["observed_at"]) - parse_time(row["published_at"])).total_seconds() / 86400
        row.update(age_days=age, cohort=cohort(row.get("duration_seconds")),
                   views_per_day=None, outlier_ratio=None, velocity_ratio=None,
                   velocity_adjusted_score=None, percentile=None,
                   baseline_sample_size=0, baseline_median_views=None,
                   baseline_median_views_per_day=None, channel_median_views=None,
                   eligibility_reason=None, provisional=False, is_outlier=False, rank=None)
        views = row.get("views")
        if age < 0:
            row["eligibility_reason"] = "future_publish_date"
        elif not row.get("available", True):
            row["eligibility_reason"] = "unavailable"
        elif row.get("is_live", False):
            row["eligibility_reason"] = "live_or_upcoming"
        elif views is None or views < 0:
            row["eligibility_reason"] = "missing_or_invalid_views"
        elif row["cohort"] is None:
            row["eligibility_reason"] = "missing_or_invalid_duration"
        elif age < 1:
            row["eligibility_reason"] = "under_24_hours"
            row["provisional"] = True
        elif age > settings.lookback_days:
            row["eligibility_reason"] = "outside_lookback"
        if views is not None and views >= 0 and age >= 0:
            row["views_per_day"] = views / max(age, 1)
        if row["eligibility_reason"] is None:
            groups[(row["channel_id"], row["cohort"])].append(row)
        rows.append(row)

    channel_views = defaultdict(list)
    baselines = {}
    for (channel_id, kind), members in groups.items():
        values = [r["views"] for r in members]
        rates = [r["views_per_day"] for r in members]
        channel_views[channel_id].extend(values)
        baselines[(channel_id, kind)] = {
            "channel_id": channel_id, "cohort": kind, "sample_size": len(values),
            "median_views": median(values), "median_views_per_day": median(rates),
            "small_sample": len(values) < 20,
        }
    for row in rows:
        values = channel_views.get(row["channel_id"], [])
        row["channel_median_views"] = median(values) if values else None
        key = (row["channel_id"], row["cohort"])
        baseline = baselines.get(key)
        if baseline:
            row.update(baseline_sample_size=baseline["sample_size"],
                       baseline_median_views=baseline["median_views"],
                       baseline_median_views_per_day=baseline["median_views_per_day"])
        if row["eligibility_reason"] is not None:
            continue
        if not baseline or baseline["sample_size"] < settings.min_sample:
            row["eligibility_reason"] = "insufficient_baseline_sample"
            continue
        if baseline["median_views"] <= 0 or baseline["median_views_per_day"] <= 0:
            row["eligibility_reason"] = "zero_baseline_median"
            continue
        row["outlier_ratio"] = row["views"] / baseline["median_views"]
        row["velocity_ratio"] = row["views_per_day"] / baseline["median_views_per_day"]
        row["velocity_adjusted_score"] = sqrt(row["outlier_ratio"] * row["velocity_ratio"])
        row["eligibility_reason"] = "eligible"
        row["is_outlier"] = (row["outlier_ratio"] >= settings.threshold and
                             row["velocity_adjusted_score"] >= settings.threshold)

    # Midrank percentile of adjusted score within the eligible channel/cohort.
    for members in groups.values():
        eligible = [r for r in members if r["velocity_adjusted_score"] is not None]
        for row in eligible:
            score = row["velocity_adjusted_score"]
            below = sum(r["velocity_adjusted_score"] < score for r in eligible)
            equal = sum(r["velocity_adjusted_score"] == score for r in eligible)
            row["percentile"] = 100 * (below + 0.5 * equal) / len(eligible)
    ranked = sorted((r for r in rows if r["velocity_adjusted_score"] is not None),
                    key=lambda r: (-r["velocity_adjusted_score"], -r["outlier_ratio"], r["video_id"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    return rows, list(baselines.values())

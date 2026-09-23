import uuid

from .scoring import score_videos
from .topics import TopicClassifier, group_topics
from .youtube import BudgetExceeded, YouTubeError


def collect(client, db, channels):
    failures, warnings, resolved, video_ids = [], [], [], []
    halted = False
    for config in channels:
        if not config.get("enabled",True):continue
        try:
            if config.get('display_name'):
                from .competitors import resolve
                resolution=resolve(client,config)
                if resolution['status']!='RESOLVED':
                    error=BudgetExceeded if resolution.get('error_type')=='BudgetExceeded' else YouTubeError
                    raise error(resolution.get('reason','Unresolved channel'))
                channel=resolution['channel']
                channel.update({k:config[k] for k in ('market_cohort','source_role','max_uploads','window_days','weight') if k in config})
            else:channel = client.resolve_channel(config)
            db.save_channel(channel)
            ids, capped = client.uploads(channel)
            resolved.append(channel)
            video_ids.extend(ids)
            if capped:
                warnings.append(f"{channel['name']}: collection capped at {channel.get('max_uploads',client.settings.max_uploads)} uploads")
        except (YouTubeError, KeyError, ValueError, TypeError) as exc:
            message = str(exc) if isinstance(exc, YouTubeError) else "Malformed channel response"
            failures.append(f"{config['name']}: {message}")
            if isinstance(exc, BudgetExceeded):
                halted = True
                break
    ids = list(dict.fromkeys(video_ids))
    rows = []
    if not halted:
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            try:
                fetched = client.videos(batch)
                valid_ids = {c["channel_id"] for c in resolved}
                fetched = [r for r in fetched if r["channel_id"] in valid_ids and r["video_id"] in batch]
                missing = set(batch) - {r["video_id"] for r in fetched}
                if missing:
                    warnings.append(f"{len(missing)} video(s) unavailable in API batch: " + ", ".join(sorted(missing)))
                    # Preserve previous metadata if present, but explicitly invalidate it.
                    old = {r["video_id"]: r for r in db.load_videos()}
                    for video_id in missing:
                        if video_id in old:
                            unavailable = old[video_id]
                            unavailable.update(available=False, views=None, likes=None, comments=None)
                            fetched.append(unavailable)
                db.save_videos(fetched)
                rows.extend(fetched)
            except (YouTubeError, KeyError, ValueError, TypeError) as exc:
                message = str(exc) if isinstance(exc, YouTubeError) else "Malformed video response"
                failures.append(f"Video batch {start // 50 + 1}: {message}")
                if isinstance(exc, BudgetExceeded):
                    break
    return rows, resolved, failures, warnings


def analyze(videos, channels, settings, classifier: TopicClassifier, now,
            mode, usage, failures=None, warnings=None):
    if any('window_days' in c for c in channels):
        from dataclasses import replace
        profiles={c['channel_id']:c for c in channels};rows=[];baselines=[]
        for channel_id in sorted({v['channel_id'] for v in videos}):
            profile=profiles.get(channel_id,{})
            scored,base=score_videos([v for v in videos if v['channel_id']==channel_id],replace(settings,lookback_days=profile.get('window_days',settings.lookback_days)))
            rows.extend(scored);baselines.extend(base)
        ranked=sorted((r for r in rows if r['velocity_adjusted_score'] is not None),key=lambda r:(-r['velocity_adjusted_score'],-r['outlier_ratio'],r['video_id']))
        for rank,row in enumerate(ranked,1):row['rank']=rank
    else:rows, baselines = score_videos(videos, settings)
    for row in rows:
        row["radar_topics"] = classifier.classify(row)
    topics = group_topics(rows, classifier)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["channel_id"], r["video_id"]))
    return {"schema_version": "1.0", "module": "Radar", "score_version": "1.0",
            "run_id": str(uuid.uuid4()), "generated_at": now.isoformat(),
            "metadata": {"mode": mode, "settings": settings.to_dict(),
                         "classifier": {"name": classifier.name, "version": classifier.version,
                                        "config_hash": getattr(classifier, "config_hash", None)},
                         "channels_processed": len(channels), "videos_processed": len(rows),
                         "channels": channels, "usage": usage,
                         "partial_failures": failures or [], "warnings": warnings or [],
                         "metrics_source": "Radar-derived heuristics; not YouTube metrics",
                         "percentile_definition": "100 * (lower scores + 0.5 * tied scores) / cohort size",
                         "status": "partial" if failures else "complete"},
            "baselines": baselines, "videos": rows,
            "outliers": [r for r in rows if r["is_outlier"]], "topics": topics}

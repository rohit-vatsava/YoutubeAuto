from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Settings:
    lookback_days: int = 90
    max_uploads: int = 100
    min_sample: int = 10
    cache_hours: int = 6
    channel_cache_days: int = 7
    request_budget: int = 100
    threshold: float = 2.0

    def __post_init__(self):
        if min(self.lookback_days, self.max_uploads, self.min_sample,
               self.cache_hours, self.channel_cache_days, self.request_budget) <= 0:
            raise ValueError("All settings must be positive")

    def to_dict(self):
        return asdict(self)

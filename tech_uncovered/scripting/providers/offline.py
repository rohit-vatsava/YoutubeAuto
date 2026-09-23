from .fixtures import FixtureResearchProvider


class OfflineResearchProvider(FixtureResearchProvider):
    """Explicit supplied evidence only; never silently falls back to live calls."""
    name,version='offline-fixture','1'

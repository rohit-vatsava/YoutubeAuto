from typing import Protocol
from .models import SourceRecord


class ResearchProvider(Protocol):
    name: str
    version: str
    def search(self, query: str, *, question_id: str) -> list[dict]: ...
    def fetch(self, url: str) -> SourceRecord: ...


class ResearchPlanner(Protocol):
    name: str
    version: str
    def plan(self, selected: dict, config: dict, now: str) -> dict: ...


class ResearchSynthesizer(Protocol):
    name: str
    version: str
    def synthesize(self, plan: dict, sources: list[dict], selected: dict) -> dict: ...


class ScriptGenerator(Protocol):
    name: str
    version: str
    def refine(self, packet: dict, selected: dict) -> dict: ...
    def outline(self, packet: dict, angle: dict) -> dict: ...
    def generate(self, packet: dict, angle: dict, outline: dict, feedback: dict | None = None) -> dict: ...


class ScriptFactChecker(Protocol):
    name: str
    version: str
    def check(self, draft: dict, packet: dict, angle: dict, now: str) -> dict: ...


class ScriptQualityReviewer(Protocol):
    name: str
    version: str
    def review(self, draft: dict, packet: dict, selected: dict) -> dict: ...


class StoryResolver(Protocol):
    """Optional preflight capability, separate from full research synthesis."""
    def resolve_story(self, selected: dict, limits: dict) -> tuple[dict, list[dict]]: ...

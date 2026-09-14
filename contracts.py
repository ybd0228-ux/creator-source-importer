"""Stable data and component boundaries for the import pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class SourceAdapter(Protocol):
    def metadata(self, value: str, work: Path) -> dict[str, Any]: ...
    def download(self, value: str, work: Path, update: Callable[..., None]) -> Path: ...


class Transcriber(Protocol):
    def __call__(self, media: Path, work: Path, model: str, language: str) -> dict[str, Any]: ...


class Exporter(Protocol):
    def render(self, record: "SourceRecord", model: str, input_value: str) -> tuple[str, str]: ...
    def publish(self, root: Path, record: "SourceRecord", markdown: str, raw_json: str) -> Path: ...


@dataclass
class SourceRecord:
    platform: str
    source_id: str
    title: str
    creator: str
    creator_id: str | None
    published_at: str | None
    duration: float | None
    source_url: str | None
    description: str
    thumbnail: str | None
    local_media_path: str | None
    language: str | None
    transcript: str
    timestamp_transcript: list[dict[str, Any]]
    imported_at: str
    legacy: dict[str, Any]

    def metadata(self):
        data = {
            "id": self.source_id,
            "platform": self.platform,
            "title": self.title,
            "channel": self.creator,
            "creator_id": self.creator_id,
            "channel_id": self.creator_id,
            "upload_date": self.published_at.replace("-", "") if self.published_at else None,
            "duration": self.duration,
            "source_url": self.source_url,
            "description": self.description,
            "thumbnail": self.thumbnail,
            "local_media_path": self.local_media_path,
            "imported_at": self.imported_at,
        }
        data.update(self.legacy)
        return data

    def transcription(self, performance=None):
        data = {
            "text": self.transcript,
            "segments": self.timestamp_transcript,
            "language": self.language,
        }
        if performance:
            data["performance"] = performance
        return data

    def as_dict(self):
        return asdict(self)

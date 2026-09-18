"""Media acquisition, local transcription and Markdown export."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yaml

from contracts import SourceRecord

PROJECT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATE = Path(os.environ.get(
    "CSI_STATE_DIR",
    Path.home() / "Library/Application Support/Creator Source Importer",
)).expanduser()
VERSION = "0.7.1"
MODELS = {
    "standard": "mlx-community/whisper-large-v3-turbo",
    "high_quality": "mlx-community/whisper-large-v3-mlx",
}
DEFAULT_MODEL = MODELS["standard"]
PLATFORM_ID_FIELDS = {
    "youtube": "video_id",
    "xiaohongshu": "note_id",
    "bilibili": "bvid",
    "local": "source_id",
}
PUBLIC_PLATFORM_LABELS = {
    "youtube": ("油管", "原视频"),
    "bilibili": ("B站", "原视频"),
    "xiaohongshu": ("小某书 Experimental", "原内容"),
    "local": ("本地媒体", "原文件"),
}
LOCAL_MEDIA_SUFFIXES = {".mp3", ".m4a", ".wav", ".mp4", ".mov"}
XHS_PROFILE = STATE / "xhs-chrome-profile"
XHS_BROWSER = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
XHS_TIMEZONE = ZoneInfo("Asia/Shanghai")
XHS_RATE_FILE = STATE / "xhs-rate-limit.json"
XHS_MIN_INTERVAL = 15
XHS_DAILY_LIMIT = 30
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


class TaskCancelled(Exception):
    pass


def video_id(url):
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or p.username or p.password or p.port:
        raise ValueError("请输入完整的油管视频网址（https://…）。")
    host = (p.hostname or "").lower()
    parts = p.path.strip("/").split("/")
    ident = ""
    if host == "youtu.be" and len(parts) == 1:
        ident = parts[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if p.path == "/watch":
            ident = parse_qs(p.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
            ident = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", ident):
        raise ValueError("仅支持单条油管视频；不支持频道、播放列表或其他网站。")
    return ident


def xiaohongshu_id(url):
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or p.username or p.password or p.port:
        raise ValueError("请输入完整的小某书内容网址（https://…）。")
    if (p.hostname or "").lower() not in {"xiaohongshu.com", "www.xiaohongshu.com"}:
        raise ValueError("不是受支持的小某书网址。")
    match = re.fullmatch(r"/(?:explore|discovery/item)/([0-9a-fA-F]{24})/?", p.path)
    if not match:
        raise ValueError("仅支持单条小某书内容的完整网址。")
    return match.group(1).lower()


def bilibili_id(url):
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or p.username or p.password or p.port:
        raise ValueError("请输入完整的 B站视频网址（https://…）。")
    if (p.hostname or "").lower() not in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        raise ValueError("不是受支持的 B站网址。")
    match = re.fullmatch(r"/video/(BV[A-Za-z0-9]{10})/?", p.path)
    if not match:
        raise ValueError("仅支持单条 B站 BV 视频的完整网址。")
    return match.group(1)


def bilibili_url(ident):
    return f"https://www.bilibili.com/video/{ident}/"


def local_media_path(value):
    raw = str(value).strip()
    parsed = urlparse(raw)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise ValueError("本地文件地址无效。")
        from urllib.parse import unquote
        path = Path(unquote(parsed.path))
    else:
        if parsed.scheme:
            raise ValueError("不支持这个来源地址。")
        path = Path(raw).expanduser()
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("请选择一个已经存在的本地媒体文件。")
    if path.suffix.lower() not in LOCAL_MEDIA_SUFFIXES:
        raise ValueError("本地媒体仅支持 MP3、M4A、WAV、MP4 和 MOV。")
    return path.resolve()


def file_content_id(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity(value):
    raw = str(value).strip()
    host = (urlparse(raw).hostname or "").lower()
    if host in {"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        return "youtube", video_id(raw)
    if host in {"xiaohongshu.com", "www.xiaohongshu.com"}:
        return "xiaohongshu", xiaohongshu_id(raw)
    if host in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        return "bilibili", bilibili_id(raw)
    if not urlparse(raw).scheme or urlparse(raw).scheme == "file":
        path = local_media_path(raw)
        return "local", file_content_id(path)
    raise ValueError("仅支持油管、B站、小某书单条内容网址，或受支持的本地媒体文件。")


def xhs_date(note_id):
    try:
        stamp = int(note_id[:8], 16)
    except (TypeError, ValueError):
        return None
    if not 1_000_000_000 < stamp < 4_000_000_000:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).astimezone(XHS_TIMEZONE).strftime("%Y%m%d")


def safe_xhs_media_url(url):
    raw = str(url or "")
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or parsed.port or not host.endswith(".xhscdn.com"):
        raise ValueError("小某书返回了不安全的视频地址，已停止下载。")
    if parsed.scheme == "http":
        parsed = parsed._replace(scheme="https")
    if parsed.scheme != "https":
        raise ValueError("小某书返回了不安全的视频地址，已停止下载。")
    return parsed.geturl()


def xhs_request_slot(path=XHS_RATE_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        try:
            data = json.load(handle)
        except (json.JSONDecodeError, ValueError):
            data = {}
        today = datetime.now(XHS_TIMEZONE).strftime("%Y-%m-%d")
        count = data.get("count", 0) if data.get("date") == today else 0
        if count >= XHS_DAILY_LIMIT:
            raise RuntimeError(f"小某书今日已达到 {XHS_DAILY_LIMIT} 次详情请求上限，请明天再试。")
        wait = XHS_MIN_INTERVAL - (time.time() - float(data.get("last_request", 0)))
        if wait > 0:
            time.sleep(wait)
        data = {"date": today, "count": count + 1, "last_request": time.time()}
        handle.seek(0)
        handle.truncate()
        json.dump(data, handle)
        handle.flush()
        os.fsync(handle.fileno())


def safe_name(value, fallback):
    name = unicodedata.normalize("NFC", str(value or ""))
    name = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|\[\]#^]', "_", name).strip(" .")
    # macOS component limit is in bytes. Leave room for video ID and extension.
    name = name.encode("utf-8")[:180].decode("utf-8", errors="ignore").rstrip(" .")
    return name or fallback


def timestamp(seconds):
    s = max(0, int(float(seconds or 0)))
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


def published_date(meta):
    date = str(meta.get("upload_date") or "")
    return f"{date[:4]}-{date[4:6]}-{date[6:8]}" if re.fullmatch(r"\d{8}", date) else None


def source_record(meta, transcript):
    return SourceRecord(
        platform=meta.get("platform") or "youtube",
        source_id=meta["id"],
        title=meta.get("title") or meta["id"],
        creator=meta.get("channel") or meta.get("uploader") or "未知频道",
        creator_id=meta.get("creator_id") or meta.get("channel_id") or meta.get("uploader_id"),
        published_at=published_date(meta),
        duration=meta.get("duration"),
        source_url=meta.get("source_url") or meta.get("webpage_url"),
        description=meta.get("description") or "",
        thumbnail=meta.get("thumbnail"),
        local_media_path=meta.get("local_media_path"),
        language=transcript.get("language"),
        transcript=transcript.get("text") or "",
        timestamp_transcript=transcript.get("segments") or [],
        imported_at=meta.get("imported_at") or datetime.now().astimezone().isoformat(timespec="seconds"),
        legacy={key: meta.get(key) for key in ("uploader", "uploader_id") if meta.get(key)},
    )


def dated_title(meta):
    title = meta.get("title") or meta["id"]
    return f"{published_date(meta) or '日期未知'} {title}"


STRONG_STARTERS = (
    "但是", "不过", "然而", "所以", "因此", "其实", "当然", "同时", "另外", "而且",
    "比如", "例如", "换句话说", "也就是说", "总之", "最后", "首先", "其次", "第二", "第三",
    "那如果", "那么", "那成年人", "那同时", "问题是", "原因是", "这意味着",
    "无条件的爱", "安全的关系", "爱一个人", "成年人仍然", "我们可以", "我们需要",
)
QUESTION_ENDINGS = ("吗", "呢", "嘛", "吧", "对吧", "是吧", "是不是", "有没有", "为什么", "怎么")
ENDING_PUNCTUATION = "。！？；：，、,.!?;:…—\"'”’）》】」』"
INCOMPLETE_ENDINGS = ("的", "和", "或", "以及", "因为", "所以", "如果", "但是", "而", "在", "从", "对", "被", "把", "给", "为", "是", "有", "能", "会", "可以", "一个", "一种", "这个", "那种", "当中", "之中", "获益")
CONTINUATION_STARTERS = ("被", "和", "或", "以及", "同时", "而且", "而是", "因为", "但不", "以及")
DISCOURSE_PREFIXES = ("其实", "但是", "不过", "然而", "所以", "因此", "当然", "比如", "例如", "同时", "另外", "换句话说", "也就是说", "总之", "最后", "首先", "其次", "那同时呢")


def content_signature(text):
    """Compare recognized content while ignoring punctuation and layout added later."""
    return "".join(char.casefold() for char in text if char.isalnum())


def validate_transcript(transcript):
    raw = transcript.get("text", "")
    segments = transcript.get("segments", [])
    if not isinstance(raw, str) or not raw.strip() or not segments:
        raise ValueError("没有识别到有效语音或时间戳；未写入笔记，音频已保留。")
    previous = 0.0
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        if not (0 <= start <= end) or start < previous or not isinstance(segment["text"], str):
            raise ValueError("转录时间戳无效；未写入笔记。")
        previous = start
    recognized = "".join(str(segment["text"]) for segment in segments)
    if content_signature(raw) != content_signature(recognized):
        raise ValueError("原始文本与时间戳片段内容不一致；未写入笔记。")
    return raw, segments


def _separator(current, following, language, sentence_chars):
    if not current:
        return ""
    if language not in {"zh", "yue", "ja", "ko"}:
        return " "
    if current[-1] in ENDING_PUNCTUATION:
        return ""
    if current.endswith(QUESTION_ENDINGS):
        return "？"
    if sentence_chars >= 14 and following.startswith(STRONG_STARTERS):
        return "。"
    return "，"


def _decorate(text, language):
    if language not in {"zh", "yue", "ja", "ko"}:
        return text
    decorated = text
    for prefix in DISCOURSE_PREFIXES:
        if decorated.startswith(prefix) and len(decorated) >= len(prefix) + 5:
            decorated = prefix + "，" + decorated[len(prefix):]
            break
    decorated = re.sub(r"(?<![，。！？；：])(?=(对吧|是吧|是不是)$)", "，", decorated)
    return decorated


def readable_paragraphs(transcript):
    raw, segments = validate_transcript(transcript)
    language = transcript.get("language") or ""
    clean = []
    for segment in segments:
        text = str(segment["text"]).strip()
        if text:
            clean.append({"start": float(segment["start"]), "end": float(segment["end"]), "text": text})
    groups = []
    start = 0
    while start < len(clean):
        best_end, best_score = None, float("-inf")
        chars = 0
        for end in range(start, len(clean)):
            chars += len(re.sub(r"\s+", "", clean[end]["text"]))
            duration = clean[end]["end"] - clean[start]["start"]
            if end == len(clean) - 1:
                best_end = end
                break
            next_text = clean[end + 1]["text"]
            pause = max(0.0, clean[end + 1]["start"] - clean[end]["end"])
            if (duration > 50 or chars > 200) and best_end is not None:
                break
            if duration >= 14 and chars >= 50:
                score = -abs(duration - 30) / 4
                if next_text.startswith(STRONG_STARTERS):
                    score += 9
                if pause >= 1.2:
                    score += 7
                if clean[end]["text"].endswith(INCOMPLETE_ENDINGS):
                    score -= 10
                if next_text.startswith(CONTINUATION_STARTERS):
                    score -= 8
                if score > best_score:
                    best_end, best_score = end, score
            if duration >= 55 or chars >= 220:
                if best_end is None:
                    best_end = end
                break
        if best_end is None:
            best_end = len(clean) - 1
        groups.append(clean[start:best_end + 1])
        start = best_end + 1
    paragraphs = []
    for group in groups:
        rendered = ""
        sentence_chars = 0
        for index, segment in enumerate(group):
            text = _decorate(segment["text"], language)
            rendered += text
            sentence_chars += len(re.sub(r"\s+", "", text))
            if index + 1 < len(group):
                separator = _separator(text, group[index + 1]["text"], language, sentence_chars)
                rendered += separator
                if separator in {"。", "！", "？", ".", "!", "?"}:
                    sentence_chars = 0
        if rendered and rendered[-1] not in ENDING_PUNCTUATION:
            rendered += "？" if rendered.endswith(QUESTION_ENDINGS) else ("。" if language in {"zh", "yue", "ja", "ko"} else ".")
        paragraphs.append({"start": group[0]["start"], "end": group[-1]["end"], "text": rendered})
    readable = "".join(paragraph["text"] for paragraph in paragraphs)
    if content_signature(readable) != content_signature(raw):
        raise ValueError("可读转录改变了原始文字；为保护原文，未写入笔记。")
    return paragraphs


def render_artifacts(meta, transcript, model, input_url):
    raw, segments = validate_transcript(transcript)
    paragraphs = readable_paragraphs(transcript)
    published = published_date(meta)
    channel = meta.get("channel") or meta.get("uploader") or "未知频道"
    title = meta.get("title") or meta["id"]
    platform = meta.get("platform") or "youtube"
    if platform not in PUBLIC_PLATFORM_LABELS:
        raise ValueError("不支持的来源平台。")
    source_label, source_name = PUBLIC_PLATFORM_LABELS[platform]
    fallback_urls = {
        "youtube": f"https://www.youtube.com/watch?v={meta['id']}",
        "xiaohongshu": input_url,
        "bilibili": bilibili_url(meta["id"]),
        "local": None,
    }
    url = meta.get("source_url") or fallback_urls[platform]
    input_path = str(meta.get("local_media_path") or "") or None
    stored_input_url = None if platform == "local" else (input_url if platform == "youtube" else url)
    creator_id = meta.get("creator_id") or meta.get("channel_id") or meta.get("uploader_id")
    fm = dict(type="media_source" if platform == "local" else "web_source",
              source_type=platform, platform=platform, source_id=meta["id"], creator=channel,
              creator_id=creator_id, channel=channel, channel_id=creator_id, title=title,
              source_url=url, input_url=stored_input_url, input_path=input_path,
              local_media_path=input_path, published_at=published,
              duration=timestamp(meta.get("duration")), duration_seconds=meta.get("duration"),
              language=transcript.get("language"), transcript_engine="mlx-whisper",
              transcript_model=model,
              imported_at=meta.get("imported_at") or datetime.now().astimezone().isoformat(timespec="seconds"),
              transcript_formatted_at=datetime.now().astimezone().isoformat(timespec="seconds"),
              transcript_format="semantic_paragraphs", paragraph_count=len(paragraphs),
              raw_transcript_file=f"_raw/{meta['id']}.json", thumbnail=meta.get("thumbnail"),
              description=meta.get("description") or "")
    legacy_id_field = PLATFORM_ID_FIELDS[platform]
    if legacy_id_field != "source_id":
        fm[legacy_id_field] = meta["id"]
    fm = {key: value for key, value in fm.items() if value is not None}
    readable = "\n\n".join(
        f"### 段落 {index:02d}｜{timestamp(paragraph['start'])}–{timestamp(paragraph['end'])}\n\n{paragraph['text']}"
        for index, paragraph in enumerate(paragraphs, 1)
    )
    source_value = input_path if platform == "local" else url
    markdown = ("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n"
            f"# {dated_title(meta)}\n\n## 来源信息\n\n- 创作者：{channel}\n- 平台：{source_label}\n"
            f"- {source_name}：{source_value}\n- 发布时间：{published or '未知'}\n- 媒体时长：{fm['duration']}\n\n"
            f"## 视频简介\n\n{meta.get('description') or ''}\n\n---\n\n"
            "## 语义分段转录\n\n"
            "> 本节只增加标点、换行和段落时间范围；未删字、换词、调整顺序或生成摘要。\n\n"
            f"{readable}\n\n---\n\n## 原始转录数据\n\n"
            f"- [Whisper 原始文本与微时间戳](_raw/{meta['id']}.json)\n")
    raw_document = {
        "schema_version": 1,
        "source": {"platform": platform, "source_id": meta["id"], "title": title,
                   "creator": channel, "creator_id": creator_id, "published_at": published,
                   "duration": meta.get("duration"), "source_url": url,
                   "input_url": stored_input_url, "local_media_path": input_path,
                   "description": meta.get("description") or "", "thumbnail": meta.get("thumbnail")},
        "transcription": {"engine": "mlx-whisper", "model": model,
                          "language": transcript.get("language"), "text": raw,
                          "segments": [{"start": float(segment["start"]), "end": float(segment["end"]),
                                        "text": segment["text"]} for segment in segments]},
    }
    raw_document["source"] = {key: value for key, value in raw_document["source"].items() if value is not None}
    if legacy_id_field != "source_id":
        raw_document["source"][legacy_id_field] = meta["id"]
    if transcript.get("performance"):
        raw_document["transcription"]["performance"] = transcript["performance"]
    return markdown, json.dumps(raw_document, ensure_ascii=False, indent=2) + "\n"


def existing_notes(root, platform=None):
    found = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
        for name in files:
            path = Path(folder) / name
            if path.suffix != ".md" or path.is_symlink():
                continue
            with path.open(encoding="utf-8") as handle:
                if handle.readline().strip() != "---":
                    continue
                header = []
                for line in handle:
                    if line.strip() == "---":
                        break
                    header.append(line)
                    if len(header) > 150:
                        break
            try:
                data = yaml.safe_load("".join(header))
            except yaml.YAMLError:
                continue
            if isinstance(data, dict):
                note_platform = data.get("source_type") or data.get("platform")
                if platform and note_platform and note_platform != platform:
                    continue
                source_id = data.get("source_id") or data.get("video_id") or data.get("note_id") or data.get("bvid")
                if source_id:
                    found[str(source_id)] = path
    return found


@contextmanager
def output_lock(root, state):
    state.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20]
    with (state / f"output-{key}.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("这个目标目录已有任务运行，请等待完成后重试。") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _verified_temp(folder, prefix, suffix, content):
    fd, temp = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    path = Path(temp)
    if path.read_text(encoding="utf-8") != content:
        path.unlink(missing_ok=True)
        raise OSError("文件写入校验失败。")
    return path


def publish(root, meta, content, raw_content):
    if root.is_symlink():
        raise ValueError("平台输出目录是符号链接，为防止写入其他位置已停止。")
    root.mkdir(exist_ok=True)
    channel = root / safe_name(meta.get("channel") or meta.get("uploader"), "未知频道")
    if channel.is_symlink():
        raise ValueError("频道目录是符号链接，为防止写入其他位置已停止。")
    channel.mkdir(exist_ok=True)
    raw_folder = channel / "_raw"
    if raw_folder.is_symlink():
        raise ValueError("原始数据目录是符号链接，为防止写入其他位置已停止。")
    raw_folder.mkdir(exist_ok=True)
    raw_destination = raw_folder / f"{meta['id']}.json"
    if raw_destination.exists():
        raise FileExistsError("该视频的原始转录数据已经存在；未覆盖任何文件。")
    title = safe_name(dated_title(meta), meta["id"])
    candidates = [channel / f"{title}.md", channel / f"{title} [{meta['id']}].md"]
    note_temp = _verified_temp(channel, ".import-", ".tmp", content)
    raw_temp = _verified_temp(raw_folder, ".import-", ".tmp", raw_content)
    raw_published = False
    try:
        os.link(raw_temp, raw_destination)
        raw_published = True
        for destination in candidates:
            try:
                os.link(note_temp, destination)
                return destination
            except FileExistsError:
                continue
        raise FileExistsError("标题和视频 ID 对应的文件均已存在；未覆盖任何文件。")
    except Exception:
        if raw_published:
            raw_destination.unlink(missing_ok=True)
        raise
    finally:
        note_temp.unlink(missing_ok=True)
        raw_temp.unlink(missing_ok=True)


def ytdlp_options(log, progress=None):
    class Logger:
        def debug(self, msg):
            log.write(msg + "\n"); log.flush()
        info = debug
        warning = debug
        error = debug
    js_path = os.environ.get("CSI_JS_RUNTIME") or shutil.which("deno") or shutil.which("node")
    js_runtimes = {}
    if js_path:
        js_runtimes["deno" if Path(js_path).name.startswith("deno") else "node"] = {"path": js_path}
    ffmpeg = os.environ.get("CSI_FFMPEG") or shutil.which("ffmpeg")
    options = {"format": "bestaudio", "noplaylist": True, "quiet": True, "no_warnings": True,
               "logger": Logger(), "socket_timeout": 30, "retries": 2, "extractor_retries": 2,
               "fragment_retries": 2, "concurrent_fragment_downloads": 1,
               "js_runtimes": js_runtimes,
               "ffmpeg_location": ffmpeg}
    if progress:
        options["progress_hooks"] = [progress]
    return options


class YouTube:
    def metadata(self, url, work):
        import yt_dlp
        with (work / "download.log").open("a") as log, yt_dlp.YoutubeDL(ytdlp_options(log)) as dl:
            info = dl.extract_info(url, download=False)
            if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
                raise ValueError("暂不支持直播中或尚未开始的视频。")
            return {k: info.get(k) for k in ("id", "title", "channel", "channel_id", "uploader", "uploader_id",
                    "upload_date", "duration", "description", "thumbnail", "webpage_url")}

    def download(self, url, work, update):
        import yt_dlp
        last = [0.0]
        def progress(event):
            if time.monotonic() - last[0] > 1:
                last[0] = time.monotonic()
                total = event.get("total_bytes") or event.get("total_bytes_estimate")
                message = f"下载音频 {event.get('downloaded_bytes', 0) / total:.0%}" if total else "正在下载最佳可用音频"
                update("downloading", message)
        with (work / "download.log").open("a") as log:
            opts = ytdlp_options(log, progress)
            opts["outtmpl"] = str(work / "audio.%(ext)s")
            with yt_dlp.YoutubeDL(opts) as dl:
                info = dl.extract_info(url, download=True)
                audio = Path(dl.prepare_filename(info))
        if not audio.is_file() or audio.stat().st_size == 0:
            raise RuntimeError("下载未产生有效音频。")
        return audio


class Bilibili(YouTube):
    def metadata(self, url, work):
        meta = super().metadata(url, work)
        meta["platform"] = "bilibili"
        meta["source_url"] = bilibili_url(meta["id"])
        meta["channel_id"] = meta.get("channel_id") or meta.get("uploader_id")
        return meta


class LocalMedia:
    def metadata(self, value, work):
        path = local_media_path(value)
        modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        return {
            "id": file_content_id(path),
            "platform": "local",
            "title": path.stem,
            "channel": "本地导入",
            "creator_id": None,
            "upload_date": modified.strftime("%Y%m%d"),
            "duration": media_duration(path),
            "description": "",
            "thumbnail": None,
            "source_url": None,
            "local_media_path": str(path),
        }

    def download(self, value, work, update):
        return local_media_path(value)


XHS_EXTRACT_JS = r"""() => {
  const unwrap = value => {
    if (!value || typeof value !== 'object') return value;
    if ('_rawValue' in value) return value._rawValue;
    if ('_value' in value) return value._value;
    return value;
  };
  const state = window.__INITIAL_STATE__ || {};
  let card = null;
  const feed = unwrap(state.feed && state.feed.undertakeNote) || {};
  for (const item of (Array.isArray(feed.items) ? feed.items : [])) {
    const candidate = unwrap(item.noteCard || item);
    if (candidate && candidate.video && candidate.video.media) { card = candidate; break; }
  }
  if (!card) {
    const note = unwrap(state.note) || {};
    const detailMap = unwrap(note.noteDetailMap) || {};
    for (const raw of Object.values(detailMap)) {
      const detail = unwrap(raw) || {};
      const candidates = [unwrap(detail.note), unwrap(detail.noteDetail), detail];
      card = candidates.find(item => item && item.video && item.video.media) || null;
      if (card) break;
    }
  }
  if (!card) {
    const body = document.body ? document.body.innerText : '';
    if (body.includes('安全限制')) return {error: 'security'};
    if (/登录后|登录查看更多|手机号登录/.test(body)) return {error: 'login'};
    return {error: 'unavailable'};
  }
  const stream = (card.video && card.video.media && card.video.media.stream) || {};
  const rows = [...(Array.isArray(stream.h264) ? stream.h264 : []), ...(Array.isArray(stream.h265) ? stream.h265 : [])];
  const mediaUrls = [];
  for (const row of rows) {
    if (row.masterUrl) mediaUrls.push(row.masterUrl);
    for (const url of (row.backupUrls || [])) mediaUrls.push(url);
  }
  const image = Array.isArray(card.imageList) && card.imageList[0] ? card.imageList[0] : {};
  return {
    id: card.noteId || card.id || '', type: card.type || '', title: card.title || card.displayTitle || '',
    description: card.desc || '', channel: card.user ? (card.user.nickname || '') : '',
    channelId: card.user ? (card.user.userId || card.user.userid || '') : '',
    thumbnail: image.urlDefault || image.urlPre || '', duration: card.video ? card.video.duration : null,
    mediaUrls
  };
}"""


class Xiaohongshu:
    def __init__(self, profile=XHS_PROFILE, rate_file=XHS_RATE_FILE):
        self.profile = Path(profile).expanduser()
        self.rate_file = Path(rate_file).expanduser()
        self.media_urls = []

    def metadata(self, url, work):
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
        ident = xiaohongshu_id(url)
        if not self.profile.is_dir():
            raise RuntimeError("小某书需要登录。请先运行专用登录窗口。")
        xhs_request_slot(self.rate_file)
        try:
            with sync_playwright() as playwright:
                options = {"user_data_dir": str(self.profile), "headless": True,
                           "viewport": {"width": 1440, "height": 900}}
                if XHS_BROWSER.is_file():
                    options["executable_path"] = str(XHS_BROWSER)
                context = playwright.chromium.launch_persistent_context(**options)
                try:
                    page = context.new_page()
                    try:
                        page.goto(url, wait_until="commit", timeout=30_000)
                    except PlaywrightError:
                        if page.is_closed():
                            raise
                    detail = {"error": "unavailable"}
                    for _ in range(30):
                        try:
                            detail = page.evaluate(XHS_EXTRACT_JS)
                            if not detail.get("error") or detail.get("error") in {"login", "security"}:
                                break
                        except PlaywrightError:
                            pass
                        time.sleep(0.5)
                finally:
                    context.close()
        except Exception as exc:
            message = str(exc)
            if "ProcessSingleton" in message or "user data directory" in message.lower():
                raise RuntimeError("小某书专用浏览器正在使用，请关闭该窗口后重试。") from None
            raise
        if detail.get("error") == "login":
            raise RuntimeError("小某书登录状态已失效，请重新登录后再试。")
        if detail.get("error") == "security":
            raise RuntimeError("小某书对该链接触发了安全限制；请重新复制当前有效链接后重试。")
        if detail.get("error") or not detail.get("mediaUrls"):
            raise RuntimeError("没有从小某书详情页取得可下载的视频流；该内容可能不是视频或暂时不可用。")
        returned = str(detail.get("id") or ident).lower()
        if returned != ident:
            raise ValueError("小某书返回的内容 ID 与输入不一致。")
        media_urls = []
        for item in detail["mediaUrls"]:
            try:
                media_urls.append(safe_xhs_media_url(item))
            except ValueError:
                continue
        self.media_urls = list(dict.fromkeys(media_urls))
        if not self.media_urls:
            raise RuntimeError("小某书没有返回可信的视频下载地址。")
        try:
            duration = float(detail.get("duration"))
            if duration > 10_000:
                duration /= 1000
        except (TypeError, ValueError):
            duration = None
        return {"id": ident, "platform": "xiaohongshu", "title": detail.get("title") or ident,
                "channel": detail.get("channel") or "未知作者", "channel_id": detail.get("channelId"),
                "upload_date": xhs_date(ident), "duration": duration, "description": detail.get("description") or "",
                "thumbnail": detail.get("thumbnail"), "source_url": f"https://www.xiaohongshu.com/explore/{ident}"}

    def download(self, url, work, update):
        if not self.media_urls:
            raise RuntimeError("小某书视频地址尚未解析。")
        destination = work / "media.mp4"
        errors = []
        for media_url in self.media_urls:
            try:
                request = Request(media_url, headers={
                    "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
                    "Referer": "https://www.xiaohongshu.com/",
                })
                with urlopen(request, timeout=60) as response, destination.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                if destination.stat().st_size and media_duration(destination):
                    return destination
                raise RuntimeError("下载内容不是有效媒体文件。")
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                destination.unlink(missing_ok=True)
        raise RuntimeError("小某书视频下载失败。" + ("\n" + errors[-1] if errors else ""))


def media_duration(path):
    ffprobe = os.environ.get("CSI_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30)
    if completed.returncode:
        return None
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return None


def transcribe(audio, work, model, language):
    ffmpeg = os.environ.get("CSI_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg or not Path(ffmpeg).is_file():
        raise RuntimeError("应用内置的媒体处理组件缺失，请重新安装应用。")
    result = work / "transcript.json"
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--transcribe-worker", str(audio), str(result), model, language]
    else:
        command = [sys.executable, str(PROJECT / "transcribe_worker.py"), str(audio), str(result), model, language]
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join([str(Path(ffmpeg).parent), environment.get("PATH", "")])
    with (work / "transcription.log").open("w") as log:
        completed = subprocess.run(command, stdout=log, stderr=log, timeout=7200, env=environment)
    if completed.returncode:
        detail = (work / "transcription.log").read_text(errors="replace")[-1800:]
        raise RuntimeError(f"本地转录失败（可能是模型下载、内存或音频问题）：\n{detail}")
    return json.loads(result.read_text(encoding="utf-8"))


class MlxWhisperTranscriber:
    def __call__(self, audio, work, model, language):
        return transcribe(audio, work, model, language)


class MarkdownExporter:
    def render(self, record, model, input_value, performance=None):
        return render_artifacts(record.metadata(), record.transcription(performance), model, input_value)

    def publish(self, root, record, markdown, raw_json):
        return publish(root, record.metadata(), markdown, raw_json)


def friendly_error(exc):
    message = str(exc)
    lower = message.lower()
    if "小红书" in message or "小某书" in message:
        return message.replace("小红书", "小某书")
    if any(s in lower for s in ("sign in", "login", "age-restricted", "private video", "not a bot")):
        return "无法读取该视频。它可能需要登录、年龄验证，或人工验证。"
    if any(s in lower for s in ("not available", "unavailable", "removed", "country", "region")):
        return "无法读取该视频。它可能已删除、不可访问或受地区限制。"
    if any(s in lower for s in ("timed out", "connection", "certificate", "network")):
        return "网络连接失败，请检查网络后重试。"
    if any(s in lower for s in ("no space", "disk full", "enospc")):
        return "磁盘空间不足，请释放空间后重试。"
    if any(s in lower for s in ("permission denied", "read-only file system")):
        return "无法写入保存目录，请检查文件夹权限或 iCloud 状态。"
    if "403" in lower or "signature" in lower:
        return "来源拒绝了下载请求，请稍后重试或检查来源是否仍可访问。"
    if isinstance(exc, ValueError):
        return message
    return "处理失败。请重试；如仍失败，可查看技术详情。"


def run_batch(urls, output, model=None, language="auto", keep_audio=False, callback=None,
              state=STATE, backend=None, backends=None, transcriber=transcribe,
              platform_folders=None, xhs_profile=None, cancel_check=None, exporter=None):
    root = Path(output).expanduser()
    if not root.is_absolute() or not root.parent.is_dir() or root.is_symlink():
        raise ValueError("保存位置须为绝对路径，父目录必须已存在，且目标不能是符号链接。")
    model = model or DEFAULT_MODEL
    if model not in MODELS.values() or language not in {"auto", "zh", "en", "ja", "ko"}:
        raise ValueError("不支持的模型或语言。")
    selected_backends = backends or {
        "youtube": YouTube(),
        "xiaohongshu": Xiaohongshu(xhs_profile or XHS_PROFILE, Path(state) / "xhs-rate-limit.json"),
        "bilibili": Bilibili(),
        "local": LocalMedia(),
    }
    exporter = exporter or MarkdownExporter()
    results = []
    if platform_folders is None:
        roots = {
            "youtube": root,
            "xiaohongshu": root.parent / "小红书",
            "bilibili": root.parent / "Bilibili",
            "local": root.parent / "本地媒体",
        }
    else:
        required = set(PLATFORM_ID_FIELDS)
        if set(platform_folders) != required or any(
                not isinstance(name, str) or not safe_name(name, "") for name in platform_folders.values()):
            raise ValueError("平台文件夹设置无效。")
        roots = {platform: root / folder for platform, folder in platform_folders.items()}
    with output_lock(root, state):
        root.mkdir(exist_ok=True)
        known = {platform: existing_notes(destination, platform) for platform, destination in roots.items()}
        for index, value in enumerate(urls):
            item = dict(index=index, url=str(value), status="queued", message="等待处理")
            started = time.monotonic()
            work = None
            def update(status, message, **extra):
                item.update(status=status, message=message, **extra)
                if callback:
                    callback(dict(item))
            try:
                if cancel_check and cancel_check():
                    raise TaskCancelled()
                platform, ident = source_identity(value)
                item.update(platform=platform, source_id=ident)
                legacy_id_field = PLATFORM_ID_FIELDS[platform]
                if legacy_id_field != "source_id":
                    item[legacy_id_field] = ident
                target_root = roots[platform]
                if target_root.is_symlink():
                    raise ValueError("平台输出目录是符号链接，为防止写入其他位置已停止。")
                selected_backend = backend or selected_backends[platform]
                if ident in known[platform]:
                    update("skipped", "视频已存在，已跳过", path=str(known[platform][ident]))
                else:
                    work = Path(tempfile.mkdtemp(prefix=f"{platform}-{ident}-", dir=state))
                    item["work_dir"] = str(work)
                    if platform == "youtube":
                        acquisition_url = f"https://www.youtube.com/watch?v={ident}"
                    elif platform == "bilibili":
                        acquisition_url = bilibili_url(ident)
                    elif platform == "local":
                        acquisition_url = str(local_media_path(value))
                    else:
                        acquisition_url = value
                    update("metadata", "正在读取视频信息")
                    meta = selected_backend.metadata(acquisition_url, work)
                    if cancel_check and cancel_check():
                        raise TaskCancelled()
                    if meta.get("id") != ident:
                        raise ValueError("平台返回的内容 ID 与输入不一致。")
                    meta.setdefault("platform", platform)
                    item["title"] = meta.get("title")
                    (work / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
                    if platform == "local":
                        update("downloading", "正在读取本地媒体")
                    elif platform == "xiaohongshu":
                        update("downloading", "正在下载小某书视频")
                    else:
                        update("downloading", "正在下载最佳可用音频")
                    audio = selected_backend.download(acquisition_url, work, update)
                    if cancel_check and cancel_check():
                        raise TaskCancelled()
                    if not meta.get("duration"):
                        meta["duration"] = media_duration(audio)
                    (work / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
                    update("transcribing", "正在本机转录，长视频可能需要几分钟")
                    transcript = transcriber(audio, work, model, language)
                    if cancel_check and cancel_check():
                        raise TaskCancelled()
                    if "performance" in transcript:
                        item["performance"] = transcript["performance"]
                    record = source_record(meta, transcript)
                    content, raw_content = exporter.render(
                        record, model, str(value), transcript.get("performance")
                    )
                    update("saving", "正在保存完整笔记")
                    destination = exporter.publish(target_root, record, content, raw_content)
                    known[platform][ident] = destination
                    if not keep_audio:
                        try:
                            shutil.rmtree(work)
                            item.pop("work_dir", None)
                        except OSError as exc:
                            item["cleanup_warning"] = str(exc)
                    update("complete", "已保存" if "cleanup_warning" not in item else "已保存，但临时文件清理失败",
                           path=str(destination))
            except TaskCancelled:
                update("cancelled", "任务已取消", technical_detail=None)
            except Exception as exc:
                update("failed", friendly_error(exc), technical_detail=f"{type(exc).__name__}: {exc}")
            item["elapsed_seconds"] = round(time.monotonic() - started, 2)
            results.append(dict(item))
            history_item = dict(item)
            if item.get("platform") == "xiaohongshu" and item.get("note_id"):
                history_item["url"] = f"https://www.xiaohongshu.com/explore/{item['note_id']}"
            elif item.get("platform") == "bilibili" and item.get("bvid"):
                history_item["url"] = bilibili_url(item["bvid"])
            with (state / "history.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**history_item, "time": datetime.now().astimezone().isoformat()}, ensure_ascii=False) + "\n")
    return results


def main():
    parser = argparse.ArgumentParser(description="油管 / B站 / 小某书 / 本地媒体 → 本地转录 → Markdown")
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--urls-file", type=Path)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", choices=MODELS, default="standard")
    parser.add_argument("--language", choices=["auto", "zh", "en", "ja", "ko"], default="auto")
    parser.add_argument("--keep-audio", "--keep-media", dest="keep_audio", action="store_true")
    args = parser.parse_args()
    urls = args.urls + (args.urls_file.read_text().splitlines() if args.urls_file else [])
    urls = [u.strip() for u in urls if u.strip()]
    if not urls:
        parser.error("请提供一个或多个视频网址，或使用 --urls-file。")
    try:
        results = run_batch(urls, args.output, MODELS[args.model], args.language, args.keep_audio,
                            lambda item: print(json.dumps(item, ensure_ascii=False), flush=True))
    except Exception as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return int(any(i["status"] == "failed" for i in results))


if __name__ == "__main__":
    sys.exit(main())

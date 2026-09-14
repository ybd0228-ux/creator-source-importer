import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
import importer as m

RAW = " 嗯，其实啊，我觉得……\n重复，重复。  "
TRANSCRIPT = {"text": RAW, "language": "zh", "segments": [
    {"start": 0.0, "end": 2.3, "text": " 嗯，其实啊，我觉得……"},
    {"start": 2.3, "end": 5.1, "text": "\n重复，重复。  "}]}


class FakeYouTube:
    def __init__(self, fail=None):
        self.fail = fail
        self.downloads = 0

    def metadata(self, url, work):
        ident = m.video_id(url)
        if ident == self.fail:
            raise RuntimeError("Video unavailable")
        return dict(id=ident, title="同名：标题 / 特殊?", channel="中文频道/测试", channel_id="UC_test",
                    upload_date="20260912", duration=6, description="原简介\n不润色：# <> &")

    def download(self, url, work, update):
        self.downloads += 1
        path = work / "audio.m4a"
        path.write_bytes(b"test audio")
        return path


class FakeXiaohongshu:
    def __init__(self):
        self.downloads = 0

    def metadata(self, url, work):
        ident = m.xiaohongshu_id(url)
        return dict(id=ident, platform="xiaohongshu", title="小红书：视频 / 测试?", channel="测试作者",
                    channel_id="xhs_user", upload_date="20260913", duration=8,
                    description="小红书原始正文", thumbnail="https://sns-webpic-qc.xhscdn.com/test",
                    source_url=f"https://www.xiaohongshu.com/explore/{ident}")

    def download(self, url, work, update):
        self.downloads += 1
        path = work / "media.mp4"
        path.write_bytes(b"test video")
        return path


class FakeBilibili:
    def __init__(self):
        self.downloads = 0

    def metadata(self, url, work):
        ident = m.bilibili_id(url)
        return dict(id=ident, platform="bilibili", title="B站：视频 / 测试?", uploader="测试UP主",
                    channel_id="bili_user", upload_date="20260914", duration=10,
                    description="B站原始简介", thumbnail="https://i0.hdslb.com/test.jpg",
                    source_url=m.bilibili_url(ident))

    def download(self, url, work, update):
        self.downloads += 1
        path = work / "audio.m4a"
        path.write_bytes(b"test audio")
        return path


def fake_transcribe(*_args):
    return copy.deepcopy(TRANSCRIPT)


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "YouTube"
        self.state = self.base / "state"
        self.backend = FakeYouTube()

    def run_urls(self, urls, **kwargs):
        return m.run_batch(urls, self.root, state=self.state, backend=self.backend,
                           transcriber=kwargs.pop("transcriber", fake_transcribe), **kwargs)

    def test_supported_url_forms(self):
        urls = ["https://www.youtube.com/watch?v=q_F5CiCyIr8&t=233s&list=foo", "https://youtu.be/q_F5CiCyIr8?si=abc",
                "https://youtube.com/shorts/q_F5CiCyIr8", "https://m.youtube.com/watch?v=q_F5CiCyIr8",
                "https://youtube.com/live/q_F5CiCyIr8"]
        for url in urls:
            self.assertEqual(m.video_id(url), "q_F5CiCyIr8")

    def test_reject_playlist_channel_other_hosts_and_bad_ids(self):
        urls = ["https://youtube.com/playlist?list=PL", "https://youtube.com/@channel", "https://youtube.com.evil.test/watch?v=q_F5CiCyIr8",
                "file:///etc/passwd", "https://user:pass@youtube.com/watch?v=q_F5CiCyIr8", "https://youtu.be/abc",
                "https://youtube.com:8080/watch?v=q_F5CiCyIr8"]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.video_id(url)

    def test_xiaohongshu_url_validation_and_source_identity(self):
        ident = "6a7f022a000000002403c1aa"
        urls = [f"https://www.xiaohongshu.com/explore/{ident}?xsec_token=test",
                f"https://xiaohongshu.com/discovery/item/{ident}"]
        for url in urls:
            self.assertEqual(m.xiaohongshu_id(url), ident)
            self.assertEqual(m.source_identity(url), ("xiaohongshu", ident))
        for url in [f"https://xiaohongshu.com.evil.test/explore/{ident}",
                    "https://www.xiaohongshu.com/explore/bad", "https://xhslink.com/a/test"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.source_identity(url)

    def test_xiaohongshu_import_uses_sibling_folder_and_note_id(self):
        ident = "6a7f022a000000002403c1aa"
        backend = FakeXiaohongshu()
        url = f"https://www.xiaohongshu.com/explore/{ident}?xsec_token=test"
        first = m.run_batch([url], self.root, state=self.state, backend=backend, transcriber=fake_transcribe)[0]
        path = Path(first["path"])
        self.assertEqual(first["status"], "complete")
        self.assertEqual(path.parent, self.base / "小红书" / "测试作者")
        self.assertEqual(path.name, "2026-09-13 小红书：视频 _ 测试_.md")
        text = path.read_text()
        fm = yaml.safe_load(text.split("---", 2)[1])
        self.assertEqual(fm["source_type"], "xiaohongshu")
        self.assertEqual(fm["source_id"], ident)
        self.assertEqual(fm["note_id"], ident)
        self.assertNotIn("video_id", fm)
        self.assertIn("- 平台：小某书 Experimental", text)
        self.assertIn("- 原内容：https://www.xiaohongshu.com/explore/" + ident, text)
        raw = json.loads((path.parent / f"_raw/{ident}.json").read_text())
        self.assertEqual(raw["source"]["note_id"], ident)
        second = m.run_batch([url], self.root, state=self.state, backend=backend, transcriber=fake_transcribe)[0]
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(backend.downloads, 1)
        self.assertNotIn("xsec_token", (self.state / "history.jsonl").read_text())

    def test_bilibili_url_validation_and_source_identity(self):
        ident = "BV1hNNXztEgG"
        urls = [f"https://www.bilibili.com/video/{ident}/?spm_id_from=test&vd_source=test",
                f"https://m.bilibili.com/video/{ident}"]
        for url in urls:
            self.assertEqual(m.bilibili_id(url), ident)
            self.assertEqual(m.source_identity(url), ("bilibili", ident))
        for url in [f"https://bilibili.com.evil.test/video/{ident}",
                    "https://www.bilibili.com/video/BVbad", "https://b23.tv/example",
                    "https://www.bilibili.com/list/watchlater"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.source_identity(url)

    def test_bilibili_import_uses_sibling_folder_and_bvid(self):
        ident = "BV1hNNXztEgG"
        backend = FakeBilibili()
        updates = []
        url = f"https://www.bilibili.com/video/{ident}/?spm_id_from=test&vd_source=test"
        first = m.run_batch([url], self.root, state=self.state, backend=backend,
                            transcriber=fake_transcribe, callback=updates.append)[0]
        path = Path(first["path"])
        self.assertEqual(first["status"], "complete")
        self.assertEqual(path.parent, self.base / "Bilibili" / "测试UP主")
        self.assertEqual(path.name, "2026-09-14 B站：视频 _ 测试_.md")
        text = path.read_text()
        fm = yaml.safe_load(text.split("---", 2)[1])
        self.assertEqual(fm["source_type"], "bilibili")
        self.assertEqual(fm["source_id"], ident)
        self.assertEqual(fm["bvid"], ident)
        self.assertNotIn("video_id", fm)
        self.assertNotIn("note_id", fm)
        self.assertEqual(fm["source_url"], m.bilibili_url(ident))
        self.assertEqual(fm["input_url"], m.bilibili_url(ident))
        self.assertIn("- 平台：B站", text)
        self.assertIn("- 原视频：" + m.bilibili_url(ident), text)
        self.assertIn("正在下载最佳可用音频", [item["message"] for item in updates])
        self.assertNotIn("正在下载小红书视频", [item["message"] for item in updates])
        raw = json.loads((path.parent / f"_raw/{ident}.json").read_text())
        self.assertEqual(raw["source"]["bvid"], ident)
        second = m.run_batch([url], self.root, state=self.state, backend=backend, transcriber=fake_transcribe)[0]
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(backend.downloads, 1)
        history = (self.state / "history.jsonl").read_text()
        self.assertNotIn("spm_id_from", history)
        self.assertNotIn("vd_source", history)

    def test_local_media_import_and_content_hash_duplicate(self):
        media = self.base / "本地 音频.mp3"
        media.write_bytes(b"synthetic local audio")
        folders = {"youtube": "油管", "bilibili": "B站", "xiaohongshu": "小某书", "local": "本地媒体"}
        first = m.run_batch([str(media)], self.base, state=self.state, platform_folders=folders,
                            transcriber=fake_transcribe)[0]
        self.assertEqual(first["status"], "complete")
        path = Path(first["path"])
        self.assertEqual(path.parent, self.base / "本地媒体" / "本地导入")
        text = path.read_text()
        fm = yaml.safe_load(text.split("---", 2)[1])
        self.assertEqual(fm["source_type"], "local")
        self.assertEqual(fm["source_id"], first["source_id"])
        self.assertEqual(len(fm["source_id"]), 64)
        self.assertEqual(fm["input_path"], str(media.resolve()))
        self.assertIn("- 平台：本地媒体", text)
        self.assertTrue(media.is_file())
        renamed = self.base / "同内容.mov"
        renamed.write_bytes(media.read_bytes())
        second = m.run_batch([str(renamed)], self.base, state=self.state, platform_folders=folders,
                             transcriber=fake_transcribe)[0]
        self.assertEqual(second["status"], "skipped")

    def test_local_media_validation(self):
        for suffix in [".mp3", ".m4a", ".wav", ".mp4", ".mov"]:
            path = self.base / f"sample{suffix}"
            path.write_bytes(b"media")
            platform, ident = m.source_identity(str(path))
            self.assertEqual(platform, "local")
            self.assertEqual(len(ident), 64)
        bad = self.base / "sample.txt"
        bad.write_text("not media")
        for value in [str(bad), str(self.base / "missing.mp3"), "relative.mp3"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.source_identity(value)

    def test_public_platform_folder_mapping(self):
        folders = {"youtube": "油管", "bilibili": "B站", "xiaohongshu": "小某书", "local": "本地媒体"}
        result = m.run_batch(["https://youtu.be/q_F5CiCyIr8"], self.base, state=self.state,
                             platform_folders=folders, backend=self.backend,
                             transcriber=fake_transcribe)[0]
        self.assertEqual(Path(result["path"]).parent, self.base / "油管" / "中文频道_测试")

    def test_mixed_platform_batch(self):
        xhs_id = "6a7f022a000000002403c1aa"
        bili_id = "BV1hNNXztEgG"
        urls = ["https://youtu.be/q_F5CiCyIr8", f"https://www.xiaohongshu.com/explore/{xhs_id}",
                f"https://www.bilibili.com/video/{bili_id}/"]
        results = m.run_batch(urls, self.root, state=self.state,
                              backends={"youtube": FakeYouTube(), "xiaohongshu": FakeXiaohongshu(),
                                        "bilibili": FakeBilibili()},
                              transcriber=fake_transcribe)
        self.assertEqual([item["status"] for item in results], ["complete", "complete", "complete"])
        self.assertTrue(list(self.root.rglob("*.md")))
        self.assertTrue(list((self.base / "小红书").rglob("*.md")))
        self.assertTrue(list((self.base / "Bilibili").rglob("*.md")))

    def test_xiaohongshu_media_url_must_use_https_cdn(self):
        self.assertEqual(m.safe_xhs_media_url("https://sns-video-v3.xhscdn.com/a.mp4"),
                         "https://sns-video-v3.xhscdn.com/a.mp4")
        self.assertEqual(m.safe_xhs_media_url("http://sns-video-v3.xhscdn.com/a.mp4"),
                         "https://sns-video-v3.xhscdn.com/a.mp4")
        self.assertEqual(m.safe_xhs_media_url("//sns-video-v3.xhscdn.com/a.mp4"),
                         "https://sns-video-v3.xhscdn.com/a.mp4")
        for url in ["https://example.com/a.mp4",
                    "file:///tmp/a.mp4", "https://user:pass@sns-video-v3.xhscdn.com/a.mp4"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.safe_xhs_media_url(url)

    def test_batch_nine_success_one_failure_and_originals_untouched(self):
        sentinel = self.base / "existing.md"
        sentinel.write_text("original\n", encoding="utf-8")
        urls = [f"https://youtu.be/testid{i:05d}" for i in range(10)]
        self.backend.fail = "testid00003"
        results = self.run_urls(urls)
        self.assertEqual([r["status"] for r in results], ["complete"] * 3 + ["failed"] + ["complete"] * 6)
        self.assertEqual(len(list(self.root.rglob("*.md"))), 9)
        self.assertEqual(len(list(self.root.rglob("*.json"))), 9)
        self.assertEqual(sentinel.read_bytes(), b"original\n")
        self.assertEqual(len(list(self.state.rglob("audio.*"))), 0)
        self.assertEqual(len(list(self.root.rglob("*.tmp"))), 0)
        self.assertEqual(len((self.state / "history.jsonl").read_text().splitlines()), 10)

    def test_semantic_markdown_and_raw_json_roundtrip(self):
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        text = Path(result["path"]).read_text()
        self.assertEqual(Path(result["path"]).name, "2026-09-12 同名：标题 _ 特殊_.md")
        self.assertIn("# 2026-09-12 同名：标题 / 特殊?", text)
        self.assertIn("## 语义分段转录", text)
        self.assertIn("### 段落 01｜00:00:00–00:00:05", text)
        self.assertNotIn("## 原始转录\n", text)
        self.assertNotIn("## 时间戳转录\n", text)
        self.assertIn("[Whisper 原始文本与微时间戳](_raw/q_F5CiCyIr8.json)", text)
        self.assertNotIn("## AI 分析", text)
        self.assertTrue(text.endswith("[Whisper 原始文本与微时间戳](_raw/q_F5CiCyIr8.json)\n"))
        fm = yaml.safe_load(text.split("---", 2)[1])
        self.assertEqual(fm["title"], "同名：标题 / 特殊?")
        self.assertEqual(fm["source_id"], "q_F5CiCyIr8")
        self.assertEqual(fm["video_id"], "q_F5CiCyIr8")
        self.assertEqual(fm["channel_id"], "UC_test")
        self.assertEqual(fm["language"], "zh")
        self.assertEqual(fm["input_url"], "https://youtu.be/q_F5CiCyIr8")
        self.assertEqual(fm["transcript_format"], "semantic_paragraphs")
        self.assertEqual(fm["paragraph_count"], 1)
        raw_path = Path(result["path"]).parent / fm["raw_transcript_file"]
        raw = json.loads(raw_path.read_text())
        self.assertEqual(raw["transcription"]["text"], RAW)
        self.assertEqual(raw["transcription"]["segments"], TRANSCRIPT["segments"])

    def test_readable_format_preserves_recognized_character_sequence(self):
        transcript = {"text": "很多人渴望被选择然而关系有条件所以我们需要边界",
                      "language": "zh", "segments": [
                          {"start": 0, "end": 8, "text": "很多人渴望被选择"},
                          {"start": 8, "end": 19, "text": "然而关系有条件"},
                          {"start": 19, "end": 31, "text": "所以我们需要边界"}]}
        paragraphs = m.readable_paragraphs(transcript)
        readable = "".join(item["text"] for item in paragraphs)
        self.assertEqual(m.content_signature(readable), m.content_signature(transcript["text"]))
        self.assertIn("，", readable)
        self.assertTrue(readable.endswith("。"))

    def test_english_segments_keep_spaces_after_existing_punctuation(self):
        transcript = {"text": "First sentence.Second sentence.", "language": "en", "segments": [
            {"start": 0, "end": 3, "text": "First sentence."},
            {"start": 3, "end": 6, "text": "Second sentence."}]}
        readable = "".join(item["text"] for item in m.readable_paragraphs(transcript))
        self.assertEqual(readable, "First sentence. Second sentence.")
        self.assertEqual(m.content_signature(readable), m.content_signature(transcript["text"]))

    def test_long_transcript_breaks_into_bounded_paragraphs(self):
        segments = [{"start": i * 5, "end": (i + 1) * 5, "text": ("所以" if i in {5, 10} else "") + "这是一个完整的小片段内容"} for i in range(15)]
        transcript = {"text": "".join(item["text"] for item in segments), "language": "zh", "segments": segments}
        paragraphs = m.readable_paragraphs(transcript)
        self.assertGreaterEqual(len(paragraphs), 2)
        self.assertTrue(all(item["end"] - item["start"] <= 50 for item in paragraphs))

    def test_raw_and_segment_content_mismatch_is_rejected(self):
        bad = copy.deepcopy(TRANSCRIPT)
        bad["segments"][1]["text"] = "内容被改变"
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"], transcriber=lambda *_: bad)[0]
        self.assertEqual(result["status"], "failed")
        self.assertFalse(list(self.root.rglob("*.md")))
        self.assertFalse(list(self.root.rglob("*.json")))

    def test_duplicate_survives_rename_and_restart(self):
        first = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        renamed = self.root / "manually-renamed.md"
        Path(first["path"]).rename(renamed)
        before = renamed.read_bytes()
        second = self.run_urls(["https://www.youtube.com/watch?v=q_F5CiCyIr8&t=5"])[0]
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(second["path"], str(renamed))
        self.assertEqual(self.backend.downloads, 1)
        self.assertEqual(renamed.read_bytes(), before)

    def test_duplicate_in_same_batch(self):
        results = self.run_urls(["https://youtu.be/q_F5CiCyIr8"] * 2)
        self.assertEqual([r["status"] for r in results], ["complete", "skipped"])

    def test_title_collision_never_overwrites(self):
        results = self.run_urls(["https://youtu.be/q_F5CiCyIr8", "https://youtu.be/mGibEMTbpRc"])
        paths = [Path(r["path"]) for r in results]
        self.assertNotEqual(paths[0], paths[1])
        self.assertIn("[mGibEMTbpRc]", paths[1].name)
        self.assertIn("video_id: q_F5CiCyIr8", paths[0].read_text())
        self.assertTrue((paths[0].parent / "_raw/q_F5CiCyIr8.json").is_file())
        self.assertTrue((paths[1].parent / "_raw/mGibEMTbpRc.json").is_file())

    def test_missing_publish_date_is_labeled_without_guessing(self):
        class MissingDateYouTube(FakeYouTube):
            def metadata(self, url, work):
                meta = super().metadata(url, work)
                meta["upload_date"] = None
                return meta
        self.backend = MissingDateYouTube()
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        self.assertEqual(Path(result["path"]).name, "日期未知 同名：标题 _ 特殊_.md")
        self.assertIn("# 日期未知 同名：标题 / 特殊?", Path(result["path"]).read_text())

    def test_safe_names_and_byte_limit(self):
        for value in ["../..", "你好" * 200, 'a/b\\c:d?e*<>|\x00', "...", "", "[x]#^title"]:
            name = m.safe_name(value, "fallback")
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertLessEqual(len(name.encode()), 180)
            self.assertFalse(name.startswith("."))

    def test_transcription_failure_keeps_audio_and_continues(self):
        calls = []
        def transcriber(*args):
            calls.append(args)
            if len(calls) == 1:
                raise RuntimeError("GPU failure")
            return fake_transcribe()
        results = self.run_urls(["https://youtu.be/q_F5CiCyIr8", "https://youtu.be/mGibEMTbpRc"], transcriber=transcriber)
        self.assertEqual([r["status"] for r in results], ["failed", "complete"])
        self.assertTrue((Path(results[0]["work_dir"]) / "audio.m4a").exists())
        self.assertEqual(len(list(self.root.rglob("*.md"))), 1)

    def test_empty_transcript_not_saved(self):
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"], transcriber=lambda *_: {"text": "", "segments": []})[0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(list(self.root.rglob("*.md")), [])
        self.assertTrue((Path(result["work_dir"]) / "audio.m4a").exists())

    def test_invalid_timestamps_rejected(self):
        bad = copy.deepcopy(TRANSCRIPT)
        bad["segments"][0]["end"] = -1
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"], transcriber=lambda *_: bad)[0]
        self.assertEqual(result["status"], "failed")

    def test_keep_audio_opt_in(self):
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"], keep_audio=True)[0]
        self.assertEqual(result["status"], "complete")
        self.assertTrue((Path(result["work_dir"]) / "audio.m4a").exists())

    def test_write_failure_retains_audio_and_no_partial_note(self):
        with patch.object(m.os, "link", side_effect=OSError("iCloud write failed")):
            result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        self.assertEqual(result["status"], "failed")
        self.assertTrue((Path(result["work_dir"]) / "audio.m4a").exists())
        self.assertFalse(list(self.root.rglob("*.md")))
        self.assertFalse(list(self.root.rglob("*.json")))
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_existing_both_collision_paths_untouched(self):
        self.root.mkdir()
        meta = self.backend.metadata("https://youtu.be/q_F5CiCyIr8", self.base)
        folder = self.root / m.safe_name(meta["channel"], "channel")
        folder.mkdir()
        title = m.safe_name(meta["title"], "title")
        paths = [folder / f"2026-09-12 {title}.md", folder / f"2026-09-12 {title} [q_F5CiCyIr8].md"]
        for path in paths:
            path.write_text("KEEP")
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        self.assertEqual(result["status"], "failed")
        self.assertTrue(all(p.read_text() == "KEEP" for p in paths))
        self.assertFalse((folder / "_raw/q_F5CiCyIr8.json").exists())

    def test_existing_raw_data_is_never_overwritten(self):
        self.root.mkdir()
        folder = self.root / "中文频道_测试"
        raw_folder = folder / "_raw"
        raw_folder.mkdir(parents=True)
        raw = raw_folder / "q_F5CiCyIr8.json"
        raw.write_text("KEEP")
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(raw.read_text(), "KEEP")
        self.assertFalse(list(folder.glob("*.md")))

    def test_destination_lock_blocks_other_batch(self):
        with m.output_lock(self.root, self.state):
            with self.assertRaisesRegex(RuntimeError, "已有任务"):
                self.run_urls(["https://youtu.be/q_F5CiCyIr8"])

    def test_symlink_channel_cannot_write_outside_root(self):
        self.root.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "中文频道_测试").symlink_to(outside, target_is_directory=True)
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        self.assertEqual(result["status"], "failed")
        self.assertFalse(list(outside.iterdir()))

    def test_symlink_raw_folder_cannot_write_outside_root(self):
        self.root.mkdir()
        channel = self.root / "中文频道_测试"
        channel.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        (channel / "_raw").symlink_to(outside, target_is_directory=True)
        result = self.run_urls(["https://youtu.be/q_F5CiCyIr8"])[0]
        self.assertEqual(result["status"], "failed")
        self.assertFalse(list(outside.iterdir()))

    def test_missing_destination_parent_rejected(self):
        with self.assertRaises(ValueError):
            m.run_batch(["https://youtu.be/q_F5CiCyIr8"], self.base / "missing" / "YouTube", state=self.state)


if __name__ == "__main__":
    unittest.main(verbosity=2)

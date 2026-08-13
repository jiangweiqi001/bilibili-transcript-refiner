import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.finalize_transcript import (
    Correction,
    Uncertainty,
    _read_corrections,
    finalize_transcript,
    render_corrected,
)
from scripts.transcript_contract import (
    Segment,
    exclusive_job_lock,
    read_jsonl,
    write_jsonl_atomic,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "source_url": "https://www.bilibili.com/video/BV1rnGt61E4j/?p=1",
            "bvid": "BV1rnGt61E4j",
            "page": 1,
            "title": '标题中有"引号"',
            "uploader": "测试UP主",
            "duration": "00:00:59.980",
        }
        self.raw = [
            Segment(0, 18_000, "大家好今天开始"),
            Segment(18_000, 25_000, "这里使用的是费马平方和定理"),
            Segment(25_000, 30_000, "需要一个便利性条件"),
        ]

    def test_renders_fixed_metadata_body_and_uncertainty_summary(self):
        corrections = [
            Correction(0, 18_000, "大家好，今天开始。", ()),
            Correction(18_000, 25_000, "这里使用的是费马平方和定理。", ()),
            Correction(
                25_000,
                30_000,
                "需要一个[疑似：遍历性]条件。",
                (
                    Uncertainty(
                        "[疑似：遍历性]", "也可能是“保测性”，音频不足以确认。"
                    ),
                ),
            ),
        ]
        doc = render_corrected(self.metadata, self.raw, corrections, status="complete")
        self.assertIn('title: "标题中有\\"引号\\""', doc)
        self.assertIn('asr_model: "SenseVoiceSmall"', doc)
        self.assertIn('correction_mode: "faithful"', doc)
        self.assertIn('status: "complete"', doc)
        self.assertIn(
            "[00:00:18.000] 这里使用的是费马平方和定理。", doc
        )
        self.assertIn(
            "- [00:00:25.000] `[疑似：遍历性]`：也可能是“保测性”，音频不足以确认。",
            doc,
        )

    def test_no_uncertainty_renders_none(self):
        corrections = [
            Correction(row.start_ms, row.end_ms, row.text + "。", ()) for row in self.raw
        ]
        doc = render_corrected(self.metadata, self.raw, corrections, status="complete")
        self.assertTrue(doc.rstrip().endswith("- 无"))

    def test_incomplete_requires_and_renders_reason(self):
        corrections = [
            Correction(row.start_ms, row.end_ms, row.text, ()) for row in self.raw
        ]
        with self.assertRaisesRegex(ValueError, "reason"):
            render_corrected(self.metadata, self.raw, corrections, status="incomplete")
        doc = render_corrected(
            self.metadata,
            self.raw,
            corrections,
            status="incomplete",
            incomplete_reason="背景音乐过强，最后一分钟无法可靠辨认。",
        )
        self.assertIn('status: "incomplete"', doc)
        self.assertIn("完整性说明：背景音乐过强", doc)

    def test_rejects_unlisted_or_invented_uncertainty_marker(self):
        with self.assertRaisesRegex(ValueError, "marker"):
            render_corrected(
                self.metadata,
                self.raw[:1],
                [Correction(0, 18_000, "这里是[听不清]。", ())],
                status="complete",
            )

    def test_checked_in_fixture_renders_the_contract(self):
        fixtures = Path(__file__).parent / "fixtures"
        raw = read_jsonl(fixtures / "raw-transcript.jsonl")
        corrections = _read_corrections(fixtures / "corrections.jsonl")
        metadata = json.loads(
            (fixtures / "metadata.json").read_text(encoding="utf-8")
        )
        doc = render_corrected(metadata, raw, corrections, status="complete")
        self.assertIn("[疑似：遍历性]", doc)
        self.assertIn("## 存疑处", doc)
        with self.assertRaisesRegex(ValueError, "marker"):
            render_corrected(
                self.metadata,
                self.raw[:1],
                [
                    Correction(
                        0,
                        18_000,
                        "这里很清楚。",
                        (Uncertainty("[听不清]", "多余记录"),),
                    )
                ],
                status="complete",
            )


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.job = self.base / "runtime" / "jobs" / "BV1rnGt61E4j"
        self.output = self.base / "科学大发现" / "逐字稿"
        self.formal = self.output / "BV1rnGt61E4j"
        self.raw = self.formal / "raw-transcript.jsonl"
        self.rows = [Segment(0, 1000, "原始一"), Segment(1200, 2200, "原始二")]
        write_jsonl_atomic(self.raw, self.rows)
        self.raw_before = self.raw.read_bytes()
        write_json(
            self.job / "metadata.json",
            {
                "source_url": "https://www.bilibili.com/video/BV1rnGt61E4j/?p=1",
                "bvid": "BV1rnGt61E4j",
                "page": 1,
                "title": "测试视频",
                "uploader": "测试UP主",
                "duration": "00:00:02.200",
            },
        )
        write_json(
            self.job / "job.json",
            {
                "schema_version": 1,
                "bvid": "BV1rnGt61E4j",
                "page": 1,
                "state": "asr_complete",
                "raw_path": str(self.raw),
                "raw_sha256": sha256(self.raw),
                "segment_count": 2,
                "runtime_provenance": {
                    "yt_dlp": {"version": "2026.07.04", "sha256": "A" * 64},
                    "ffmpeg": {"version": "9.0.1", "sha256": "B" * 64},
                    "ffprobe": {"version": "9.0.1", "sha256": "C" * 64},
                    "funasr_sensevoice": {"version": "0.1.8", "sha256": "D" * 64},
                    "funasr_vad": {"version": "0.1.8", "sha256": "E" * 64},
                    "sensevoice_model": {
                        "version": "q8",
                        "revision": "90c1c61912018b70ada0fcc024ea24aca62f2e63",
                        "sha256": "F" * 64,
                    },
                    "vad_model": {
                        "version": "main",
                        "revision": "6840bae4c5c92ee8c04faaf4db23dd0105098d7f",
                        "sha256": "1" * 64,
                    },
                },
            },
        )
        self.write_corrections(
            [
                {
                    "start": "00:00:00.000",
                    "end": "00:00:01.000",
                    "text": "原始一。",
                    "uncertainties": [],
                },
                {
                    "start": "00:00:01.200",
                    "end": "00:00:02.200",
                    "text": "原始二。",
                    "uncertainties": [],
                },
            ]
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_corrections(self, rows):
        self.job.mkdir(parents=True, exist_ok=True)
        (self.job / "corrections.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_finalizes_atomically_and_keeps_exactly_two_files(self):
        corrected = finalize_transcript(self.job, self.output, status="complete")
        self.assertEqual(corrected, (self.formal / "corrected-transcript.md").resolve())
        self.assertEqual(self.raw.read_bytes(), self.raw_before)
        self.assertEqual(
            sorted(path.name for path in self.formal.iterdir()),
            ["corrected-transcript.md", "raw-transcript.jsonl"],
        )
        self.assertNotIn(".partial-", corrected.name)
        document = corrected.read_text(encoding="utf-8")
        self.assertIn(f'raw_transcript_sha256: "{sha256(self.raw)}"', document)
        self.assertIn(
            'asr_model_revision: "90c1c61912018b70ada0fcc024ea24aca62f2e63"',
            document,
        )
        self.assertIn(f'asr_model_sha256: "{"F" * 64}"', document)
        self.assertIn('yt_dlp_version: "2026.07.04"', document)
        self.assertIn(f'yt_dlp_sha256: "{"A" * 64}"', document)
        self.assertIn('ffmpeg_version: "9.0.1"', document)
        self.assertIn(f'ffmpeg_sha256: "{"B" * 64}"', document)
        self.assertIn('ffprobe_version: "9.0.1"', document)
        self.assertIn(f'ffprobe_sha256: "{"C" * 64}"', document)
        self.assertIn('funasr_runtime_version: "0.1.8"', document)
        self.assertIn(f'funasr_runtime_sha256: "{"D" * 64}"', document)
        self.assertIn('funasr_vad_version: "0.1.8"', document)
        self.assertIn(f'funasr_vad_sha256: "{"E" * 64}"', document)
        self.assertIn('vad_model_version: "main"', document)
        self.assertIn(
            'vad_model_revision: "6840bae4c5c92ee8c04faaf4db23dd0105098d7f"',
            document,
        )
        self.assertIn(f'vad_model_sha256: "{"1" * 64}"', document)
        self.assertRegex(document, r'generated_at: "\d{4}-\d{2}-\d{2}T')
        self.assertIn("correction_high_risk_acknowledged: false", document)

    def test_finalize_rejects_a_concurrent_job_transition(self):
        with exclusive_job_lock(self.job / "job.lock"):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                finalize_transcript(self.job, self.output, status="complete")

    def test_rejects_changed_raw_hash(self):
        self.raw.write_bytes(self.raw.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            finalize_transcript(self.job, self.output, status="complete")

    def test_rejects_changed_timestamp_or_row_count(self):
        self.write_corrections(
            [
                {
                    "start": "00:00:00.001",
                    "end": "00:00:01.000",
                    "text": "校订一。",
                    "uncertainties": [],
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "count|timestamps"):
            finalize_transcript(self.job, self.output, status="complete")

    def test_rejects_unexpected_formal_file(self):
        (self.formal / "summary.md").write_text("not allowed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected deliverable"):
            finalize_transcript(self.job, self.output, status="complete")

    def test_archives_owned_stale_formal_partial_before_retrying(self):
        stale = self.formal / "corrected-transcript.md.partial-crashed"
        stale.write_text("interrupted output", encoding="utf-8")

        corrected = finalize_transcript(self.job, self.output, status="complete")

        self.assertTrue(corrected.is_file())
        self.assertFalse(stale.exists())
        archived = list(
            (self.job / "archive").glob(
                "corrected-transcript.md.partial-crashed.stale-*"
            )
        )
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_text(encoding="utf-8"), "interrupted output")

    def test_high_risk_correction_requires_explicit_audio_review_acknowledgement(self):
        self.write_corrections(
            [
                {
                    "start": "00:00:00.000",
                    "end": "00:00:01.000",
                    "text": "2025 年校订。",
                    "uncertainties": [],
                },
                {
                    "start": "00:00:01.200",
                    "end": "00:00:02.200",
                    "text": "原始二。",
                    "uncertainties": [],
                },
            ]
        )
        self.rows = [Segment(0, 1000, "2024 年原始"), self.rows[1]]
        self.raw.unlink()
        write_jsonl_atomic(self.raw, self.rows)
        manifest = json.loads((self.job / "job.json").read_text(encoding="utf-8"))
        manifest["raw_sha256"] = sha256(self.raw)
        write_json(self.job / "job.json", manifest)

        with self.assertRaisesRegex(ValueError, "high-risk"):
            finalize_transcript(self.job, self.output, status="complete")

        corrected = finalize_transcript(
            self.job,
            self.output,
            status="complete",
            acknowledge_high_risk=True,
        )
        self.assertTrue(corrected.is_file())
        audit = json.loads(
            (self.job / "correction-audit.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(audit["high_risk_count"], 1)


if __name__ == "__main__":
    unittest.main()

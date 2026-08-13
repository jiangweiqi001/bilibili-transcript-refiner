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
from scripts.review_corrections import list_review_findings, record_finding_review
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

    def test_complete_rejects_whole_row_inaudible(self):
        marker = "[听不清]"
        corrections = [
            Correction(
                0,
                18_000,
                marker,
                (Uncertainty(marker, "整段音频无法可靠辨认。"),),
            )
        ]

        with self.assertRaisesRegex(ValueError, "status incomplete"):
            render_corrected(
                self.metadata, self.raw[:1], corrections, status="complete"
            )

    def test_pairing_precedes_whole_row_inaudible_status_gate(self):
        marker = "[听不清]"
        corrections = [
            Correction(
                0,
                18_000,
                marker,
                (Uncertainty(marker, "整段音频无法可靠辨认。"),),
            )
        ]

        with self.assertRaisesRegex(ValueError, "count|timestamps"):
            render_corrected(
                self.metadata, self.raw, corrections, status="complete"
            )

    def test_complete_allows_partial_inaudible_marker(self):
        marker = "[听不清]"
        corrections = [
            Correction(
                0,
                18_000,
                f"大家好，{marker}，今天开始。",
                (Uncertainty(marker, "仅这一小段无法可靠辨认。"),),
            ),
            Correction(18_000, 25_000, self.raw[1].text, ()),
            Correction(25_000, 30_000, self.raw[2].text, ()),
        ]

        doc = render_corrected(
            self.metadata, self.raw, corrections, status="complete"
        )

        self.assertIn('status: "complete"', doc)
        self.assertIn(f"大家好，{marker}，今天开始。", doc)

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
        self.source_audio = self.job / "source.m4a"
        self.normalized_wav = self.job / "speech.wav"
        self.source_audio.parent.mkdir(parents=True, exist_ok=True)
        self.source_audio.write_bytes(b"source audio evidence")
        self.normalized_wav.write_bytes(b"normalized wav evidence")
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
                "active_run": "run-0001",
                "source_audio_path": str(self.source_audio),
                "source_audio_sha256": sha256(self.source_audio),
                "normalized_wav_path": str(self.normalized_wav),
                "normalized_wav_sha256": sha256(self.normalized_wav),
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

    def whole_row_inaudible_corrections(self, *, second_text="原始二。"):
        return [
            {
                "start": "00:00:00.000",
                "end": "00:00:01.000",
                "text": "[听不清]",
                "uncertainties": [
                    {
                        "marker": "[听不清]",
                        "note": "该段音频无法可靠辨认。",
                    }
                ],
            },
            {
                "start": "00:00:01.200",
                "end": "00:00:02.200",
                "text": second_text,
                "uncertainties": [],
            },
        ]

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
        self.assertIn(f'source_audio_sha256: "{sha256(self.source_audio)}"', document)
        self.assertIn(f'normalized_wav_sha256: "{sha256(self.normalized_wav)}"', document)
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
        self.assertIn("correction_high_risk_reviewed: false", document)

    def test_complete_rejects_whole_row_inaudible_but_incomplete_finalizes(self):
        self.write_corrections(self.whole_row_inaudible_corrections())

        with self.assertRaisesRegex(ValueError, "status incomplete"):
            finalize_transcript(self.job, self.output, status="complete")

        reviews_path = self.job / "correction-reviews.json"
        self.assertFalse(reviews_path.exists())
        reason = "首段音频无法可靠辨认。"
        corrected = finalize_transcript(
            self.job,
            self.output,
            status="incomplete",
            incomplete_reason=reason,
        )

        self.assertFalse(reviews_path.exists())
        document = corrected.read_text(encoding="utf-8")
        self.assertIn('status: "incomplete"', document)
        self.assertIn(reason, document)
        self.assertIn("[听不清]", document)
        self.assertIn("correction_high_risk_reviewed: false", document)
        audit = json.loads(
            (self.job / "correction-audit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(audit["high_risk_count"], 0)
        self.assertEqual(
            [(item["code"], item["severity"]) for item in audit["findings"]],
            [("explicit-inaudible-substitution", "info")],
        )
        job_value = json.loads(
            (self.job / "job.json").read_text(encoding="utf-8")
        )
        self.assertEqual(job_value["correction_state"], "incomplete")
        self.assertFalse(job_value["correction_high_risk_reviewed"])

    def test_complete_rejects_whole_row_inaudible_even_with_stale_review(self):
        self.write_corrections(self.whole_row_inaudible_corrections())
        write_json(
            self.job / "correction-reviews.json",
            {
                "schema_version": 1,
                "raw_sha256": "0" * 64,
                "corrections_sha256": "1" * 64,
                "reviews": [],
            },
        )

        with self.assertRaisesRegex(ValueError, "status incomplete"):
            finalize_transcript(self.job, self.output, status="complete")

        self.assertFalse((self.formal / "corrected-transcript.md").exists())

    def test_incomplete_still_requires_review_for_other_high_risk_rewrite(self):
        self.write_corrections(
            self.whole_row_inaudible_corrections(second_text="完全改写。")
        )
        clip = self.job / "runs" / "run-0001" / "clips" / "000001.wav"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"reviewable audio")

        with self.assertRaisesRegex(ValueError, "unreviewed high-risk"):
            finalize_transcript(
                self.job,
                self.output,
                status="incomplete",
                incomplete_reason="首段音频无法可靠辨认。",
            )

        audit = json.loads(
            (self.job / "correction-audit.json").read_text(encoding="utf-8")
        )
        self.assertIn(
            ("explicit-inaudible-substitution", "info"),
            [(item["code"], item["severity"]) for item in audit["findings"]],
        )
        self.assertGreaterEqual(audit["high_risk_count"], 1)

    def test_incomplete_rejects_prefix_before_writing_audit(self):
        self.write_corrections(
            [
                {
                    "start": "00:00:00.000",
                    "end": "00:00:01.000",
                    "text": "原始一。",
                    "uncertainties": [],
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "count|timestamps"):
            finalize_transcript(
                self.job,
                self.output,
                status="incomplete",
                incomplete_reason="校订尚未覆盖全部分段。",
            )

        self.assertFalse((self.job / "correction-audit.json").exists())

    def test_finalize_rejects_a_concurrent_job_transition(self):
        with exclusive_job_lock(self.job / "job.lock"):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                finalize_transcript(self.job, self.output, status="complete")

    def test_rejects_changed_raw_hash(self):
        self.raw.write_bytes(self.raw.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            finalize_transcript(self.job, self.output, status="complete")

    def test_rejects_changed_normalized_wav_hash(self):
        self.normalized_wav.write_bytes(b"tampered after transcript preparation")

        with self.assertRaisesRegex(ValueError, "normalized WAV SHA-256"):
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

    def test_high_risk_correction_requires_current_finding_level_audio_reviews(self):
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
        clip = self.job / "runs" / "run-0001" / "clips" / "000000.wav"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"reviewable audio")

        with self.assertRaisesRegex(ValueError, "unreviewed high-risk"):
            finalize_transcript(self.job, self.output, status="complete")

        findings = list_review_findings(self.job)
        self.assertGreaterEqual(len(findings), 1)
        self.assertEqual(Path(findings[0]["clip_path"]), clip.resolve())
        for finding in findings:
            record_finding_review(
                self.job,
                finding["finding_id"],
                decision="confirmed",
                note="已对照该段音频，确认校订内容。",
            )

        corrected = finalize_transcript(self.job, self.output, status="complete")
        self.assertTrue(corrected.is_file())
        document = corrected.read_text(encoding="utf-8")
        self.assertIn("correction_high_risk_reviewed: true", document)
        audit = json.loads(
            (self.job / "correction-audit.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(audit["high_risk_count"], 1)

    def test_bare_global_acknowledgement_cannot_unlock_finalization(self):
        self.write_corrections(
            [
                {
                    "start": "00:00:00.000",
                    "end": "00:00:01.000",
                    "text": "完全改写。",
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

        with self.assertRaisesRegex(ValueError, "global|finding-level"):
            finalize_transcript(
                self.job,
                self.output,
                status="complete",
                acknowledge_high_risk=True,
            )

    def test_review_rejects_an_active_run_path_escape(self):
        self.write_corrections(
            [
                {
                    "start": "00:00:00.000",
                    "end": "00:00:01.000",
                    "text": "完全改写。",
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
        manifest_path = self.job / "job.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["active_run"] = "..\\escape"
        write_json(manifest_path, manifest)

        with self.assertRaisesRegex(ValueError, "active ASR run"):
            list_review_findings(self.job)

    def test_review_records_are_invalid_after_corrections_change(self):
        self.write_corrections(
            [
                {
                    "start": "00:00:00.000",
                    "end": "00:00:01.000",
                    "text": "完全改写。",
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
        clip = self.job / "runs" / "run-0001" / "clips" / "000000.wav"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"reviewable audio")
        for finding in list_review_findings(self.job):
            record_finding_review(
                self.job,
                finding["finding_id"],
                decision="confirmed",
                note="已听音频。",
            )

        correction_rows = (self.job / "corrections.jsonl").read_text(encoding="utf-8")
        (self.job / "corrections.jsonl").write_text(
            correction_rows.replace("完全改写。", "另一种完全改写。"),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "unreviewed high-risk"):
            finalize_transcript(self.job, self.output, status="complete")


if __name__ == "__main__":
    unittest.main()

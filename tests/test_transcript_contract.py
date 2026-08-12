import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.transcript_contract import (
    Segment,
    format_timestamp,
    output_name,
    parse_bilibili_url,
    read_jsonl,
    validate_coverage,
    validate_segments,
    write_jsonl_atomic,
)


class BilibiliUrlTests(unittest.TestCase):
    def test_parse_url_and_page(self):
        parsed = parse_bilibili_url(
            "https://www.bilibili.com/video/BV1rnGt61E4j/?p=2"
        )
        self.assertEqual((parsed.bvid, parsed.page), ("BV1rnGt61E4j", 2))
        self.assertEqual(
            parsed.canonical_url,
            "https://www.bilibili.com/video/BV1rnGt61E4j/?p=2",
        )

    def test_page_defaults_to_one(self):
        parsed = parse_bilibili_url(
            "https://m.bilibili.com/video/BV1rnGt61E4j"
        )
        self.assertEqual(parsed.page, 1)

    def test_rejects_non_bilibili_host(self):
        with self.assertRaisesRegex(ValueError, "Bilibili host"):
            parse_bilibili_url("https://example.com/video/BV1rnGt61E4j")

    def test_rejects_missing_bvid(self):
        with self.assertRaisesRegex(ValueError, "BV identifier"):
            parse_bilibili_url("https://www.bilibili.com/video/av123")

    def test_rejects_nonpositive_page(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            parse_bilibili_url(
                "https://www.bilibili.com/video/BV1rnGt61E4j/?p=0"
            )

    def test_output_name_adds_page_suffix_only_after_page_one(self):
        self.assertEqual(output_name("BV1rnGt61E4j", 1), "BV1rnGt61E4j")
        self.assertEqual(output_name("BV1rnGt61E4j", 2), "BV1rnGt61E4j-p02")
        self.assertEqual(output_name("BV1rnGt61E4j", 100), "BV1rnGt61E4j-p100")


class SegmentContractTests(unittest.TestCase):
    def test_formats_global_millisecond_timestamp(self):
        self.assertEqual(format_timestamp(3_723_004), "01:02:03.004")

    def test_segment_rejects_negative_or_reversed_time(self):
        with self.assertRaises(ValueError):
            Segment(-1, 100, "甲")
        with self.assertRaises(ValueError):
            Segment(100, 100, "甲")

    def test_segment_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "nonempty"):
            Segment(0, 100, "  ")

    def test_validate_segments_rejects_overlap_and_disorder(self):
        with self.assertRaisesRegex(ValueError, "ordered"):
            validate_segments([Segment(100, 200, "乙"), Segment(0, 50, "甲")])
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_segments([Segment(0, 200, "甲"), Segment(100, 300, "乙")])

    def test_coverage_requires_one_matching_asr_row_per_vad_span(self):
        vad = [(0, 950), (1200, 2200)]
        rows = [Segment(0, 950, "甲"), Segment(1200, 2200, "乙")]
        validate_coverage(vad, rows)

        with self.assertRaisesRegex(ValueError, "count"):
            validate_coverage(vad, rows[:1])
        with self.assertRaisesRegex(ValueError, "boundaries"):
            validate_coverage(vad, [rows[0], Segment(1201, 2200, "乙")])


class JsonlTests(unittest.TestCase):
    def test_atomic_jsonl_round_trip_uses_fixed_shape(self):
        rows = [Segment(0, 950, "甲"), Segment(1200, 2200, "乙")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw-transcript.jsonl"
            write_jsonl_atomic(path, rows)
            self.assertEqual(read_jsonl(path), rows)
            self.assertEqual(
                path.read_text(encoding="utf-8").splitlines(),
                [
                    '{"start":"00:00:00.000","end":"00:00:00.950","text":"甲"}',
                    '{"start":"00:00:01.200","end":"00:00:02.200","text":"乙"}',
                ],
            )
            self.assertEqual(list(path.parent.glob("*.partial-*")), [])

    def test_atomic_writer_refuses_to_replace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw-transcript.jsonl"
            write_jsonl_atomic(path, [Segment(0, 100, "原")])
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_jsonl_atomic(path, [Segment(0, 100, "改")])
            self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(os.name == "nt", "published evidence contract targets Windows")
    def test_atomic_writer_loses_a_race_without_overwriting_the_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw-transcript.jsonl"
            original_rename = os.rename

            def install_competing_evidence(partial, destination):
                Path(destination).write_text("winner\n", encoding="utf-8")
                return original_rename(partial, destination)

            with patch(
                "scripts.transcript_contract.os.rename",
                side_effect=install_competing_evidence,
            ):
                with self.assertRaises(FileExistsError):
                    write_jsonl_atomic(path, [Segment(0, 100, "loser")])
            self.assertEqual(path.read_text(encoding="utf-8"), "winner\n")
            self.assertEqual(list(path.parent.glob("*.partial-*")), [])

    def test_reader_rejects_extra_or_reordered_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw-transcript.jsonl"
            path.write_text(
                json.dumps(
                    {"end": "00:00:00.100", "start": "00:00:00.000", "text": "甲"},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exact keys"):
                read_jsonl(path)


if __name__ == "__main__":
    unittest.main()

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.correction_contract import (
    Correction,
    audit_corrections,
    install_correction_batch,
    read_corrections,
    write_audit_report,
)
from scripts.transcript_contract import Segment, write_jsonl_atomic


def write_lines(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def correction(start: str, end: str, text: str) -> dict[str, object]:
    return {"start": start, "end": end, "text": text, "uncertainties": []}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class CorrectionCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.raw_path = self.base / "raw-transcript.jsonl"
        self.checkpoint = self.base / "job" / "corrections.jsonl"
        self.batch = self.base / "job" / "correction-batch.jsonl"
        self.raw = [
            Segment(0, 1000, "第一行有 2024 年数据"),
            Segment(1200, 2200, "第二行保留 Python3"),
            Segment(2400, 3400, "第三行结束"),
        ]
        write_jsonl_atomic(self.raw_path, self.raw)

    def tearDown(self):
        self.temp.cleanup()

    def test_installs_only_the_next_valid_batch_by_atomic_replacement(self):
        write_lines(
            self.checkpoint,
            [correction("00:00:00.000", "00:00:01.000", "第一行有 2024 年数据。")],
        )
        write_lines(
            self.batch,
            [correction("00:00:01.200", "00:00:02.200", "第二行保留 Python3。")],
        )

        result = install_correction_batch(self.raw_path, self.checkpoint, self.batch)

        rows = read_corrections(self.checkpoint)
        self.assertEqual(len(rows), 2)
        self.assertEqual(result["accepted_rows"], 2)
        self.assertEqual(result["next_index"], 2)
        self.assertFalse(result["complete"])
        self.assertTrue((self.checkpoint.parent / "correction-audit.json").is_file())
        self.assertEqual(list(self.checkpoint.parent.glob("*.partial-*")), [])

    def test_rejects_a_batch_that_does_not_start_at_first_missing_row(self):
        write_lines(
            self.checkpoint,
            [correction("00:00:00.000", "00:00:01.000", "第一行。")],
        )
        before = self.checkpoint.read_bytes()
        write_lines(
            self.batch,
            [correction("00:00:02.400", "00:00:03.400", "跳到了第三行。")],
        )

        with self.assertRaisesRegex(ValueError, "next raw row|timestamps"):
            install_correction_batch(self.raw_path, self.checkpoint, self.batch)

        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_hash_guarded_replacement_can_revise_an_accepted_suffix(self):
        write_lines(
            self.checkpoint,
            [
                correction("00:00:00.000", "00:00:01.000", "第一行有 2024 年数据。"),
                correction("00:00:01.200", "00:00:02.200", "错误接受的第二行。"),
                correction("00:00:02.400", "00:00:03.400", "错误接受的第三行。"),
            ],
        )
        expected_hash = sha256(self.checkpoint)
        write_lines(
            self.batch,
            [
                correction("00:00:01.200", "00:00:02.200", "第二行保留 Python3。"),
                correction("00:00:02.400", "00:00:03.400", "第三行结束。"),
            ],
        )

        result = install_correction_batch(
            self.raw_path,
            self.checkpoint,
            self.batch,
            replace_from=1,
            expected_corrections_sha256=expected_hash,
        )

        rows = read_corrections(self.checkpoint)
        self.assertEqual([row.text for row in rows], [
            "第一行有 2024 年数据。",
            "第二行保留 Python3。",
            "第三行结束。",
        ])
        self.assertEqual(result["replaced_from"], 1)

    def test_replacement_rejects_a_stale_corrections_hash(self):
        write_lines(
            self.checkpoint,
            [correction("00:00:00.000", "00:00:01.000", "第一行。")],
        )
        before = self.checkpoint.read_bytes()
        write_lines(
            self.batch,
            [correction("00:00:00.000", "00:00:01.000", "修订后的第一行。")],
        )

        with self.assertRaisesRegex(ValueError, "SHA-256|changed"):
            install_correction_batch(
                self.raw_path,
                self.checkpoint,
                self.batch,
                replace_from=0,
                expected_corrections_sha256="0" * 64,
            )

        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_audit_marks_protected_tokens_deletion_and_large_rewrite(self):
        corrected = [
            Correction(0, 1000, "第一行有 2025 年数据", ()),
            Correction(1200, 2200, "删掉", ()),
            Correction(2400, 3400, "完全不同内容", ()),
        ]

        findings = audit_corrections(self.raw, corrected)
        codes = {(item.row_index, item.code) for item in findings}

        self.assertIn((0, "protected-token-change"), codes)
        self.assertIn((1, "major-deletion"), codes)
        self.assertIn((2, "large-rewrite"), codes)
        self.assertTrue(all(item.severity == "high" for item in findings))

    def test_audit_protects_chinese_numerals_even_in_a_short_row(self):
        raw = [Segment(0, 1000, "共三项")]
        corrected = [Correction(0, 1000, "共四项", ())]

        findings = audit_corrections(raw, corrected)

        self.assertIn("protected-token-change", {item.code for item in findings})

    def test_audit_detects_semantic_loss_in_a_short_non_numeric_row(self):
        raw = [Segment(0, 1000, "不要")]
        corrected = [Correction(0, 1000, "好", ())]

        findings = audit_corrections(raw, corrected)

        self.assertTrue(
            {"major-deletion", "large-rewrite"}
            & {item.code for item in findings}
        )

    def test_audit_protects_token_order_and_complete_dates(self):
        raw = [Segment(0, 1000, "范围从5到10，日期2026-08-14")]
        corrected = [Correction(0, 1000, "范围从10到5，日期2026-14-08", ())]

        findings = audit_corrections(raw, corrected)

        self.assertIn("protected-token-change", {item.code for item in findings})

    def test_audit_report_assigns_hash_bound_deterministic_finding_ids(self):
        write_lines(
            self.checkpoint,
            [
                correction("00:00:00.000", "00:00:01.000", "第一行有 2025 年数据。"),
            ],
        )
        raw = self.raw[:1]
        corrected = read_corrections(self.checkpoint)

        first = write_audit_report(
            self.checkpoint.parent / "audit-1.json",
            self.raw_path,
            self.checkpoint,
            raw,
            corrected,
        )
        second = write_audit_report(
            self.checkpoint.parent / "audit-2.json",
            self.raw_path,
            self.checkpoint,
            raw,
            corrected,
        )

        first_id = first["findings"][0]["finding_id"]
        self.assertEqual(first_id, second["findings"][0]["finding_id"])
        self.assertRegex(first_id, r"^[A-F0-9]{64}$")


if __name__ == "__main__":
    unittest.main()

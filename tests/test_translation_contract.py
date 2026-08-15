import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.correction_contract import Correction, write_corrections_atomic
from scripts.translation_contract import (
    Translation,
    install_translation_batch,
    read_translations,
    validate_translation_pairing,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_lines(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def translation(start: str, end: str, source_text: str, text_zh: str) -> dict[str, object]:
    return {
        "start": start,
        "end": end,
        "source_text": source_text,
        "text_zh": text_zh,
    }


class TranslationCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.corrections_path = self.base / "job" / "corrections.jsonl"
        self.checkpoint = self.base / "job" / "translations-zh.jsonl"
        self.batch = self.base / "job" / "translation-batch.jsonl"
        self.corrections = [
            Correction(0, 1000, "Hello.", ()),
            Correction(1200, 2200, "We keep Python3.", ()),
            Correction(2400, 3400, "That is all.", ()),
        ]
        write_corrections_atomic(self.corrections_path, self.corrections)

    def tearDown(self):
        self.temp.cleanup()

    def test_installs_only_the_next_source_bound_translation_batch(self):
        write_lines(
            self.batch,
            [
                translation("00:00:00.000", "00:00:01.000", "Hello.", "你好。"),
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We keep Python3.",
                    "我们保留 Python3。",
                ),
            ],
        )

        result = install_translation_batch(
            self.corrections_path, self.checkpoint, self.batch
        )

        self.assertEqual(result["accepted_rows"], 2)
        self.assertEqual(result["next_index"], 2)
        self.assertFalse(result["complete"])
        self.assertEqual(result["translations_sha256"], sha256(self.checkpoint))
        self.assertEqual(list(self.checkpoint.parent.glob("*.partial-*")), [])

    def test_rejects_a_batch_that_skips_the_first_missing_row(self):
        write_lines(
            self.batch,
            [
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We keep Python3.",
                    "我们保留 Python3。",
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "next correction row|timestamps"):
            install_translation_batch(
                self.corrections_path, self.checkpoint, self.batch
            )

        self.assertFalse(self.checkpoint.exists())

    def test_rejects_translation_after_source_correction_changes(self):
        translations = [Translation(0, 1000, "Hello.", "你好。")]
        changed = [Correction(0, 1000, "Hello!", ())]

        with self.assertRaisesRegex(ValueError, "source text changed"):
            validate_translation_pairing(changed, translations)

    def test_hash_guarded_suffix_replacement_updates_a_bad_translation(self):
        write_lines(
            self.checkpoint,
            [
                translation("00:00:00.000", "00:00:01.000", "Hello.", "你好。"),
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We keep Python3.",
                    "错误译文。",
                ),
                translation(
                    "00:00:02.400",
                    "00:00:03.400",
                    "That is all.",
                    "错误结尾。",
                ),
            ],
        )
        expected_hash = sha256(self.checkpoint)
        write_lines(
            self.batch,
            [
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We keep Python3.",
                    "我们保留 Python3。",
                ),
                translation(
                    "00:00:02.400",
                    "00:00:03.400",
                    "That is all.",
                    "以上就是全部内容。",
                ),
            ],
        )

        result = install_translation_batch(
            self.corrections_path,
            self.checkpoint,
            self.batch,
            replace_from=1,
            expected_translations_sha256=expected_hash,
        )

        self.assertEqual(result["replaced_from"], 1)
        self.assertTrue(result["complete"])
        self.assertEqual(
            [row.text_zh for row in read_translations(self.checkpoint)],
            ["你好。", "我们保留 Python3。", "以上就是全部内容。"],
        )

    def test_replacement_rejects_a_stale_translation_hash(self):
        write_lines(
            self.checkpoint,
            [translation("00:00:00.000", "00:00:01.000", "Hello.", "你好。")],
        )
        before = self.checkpoint.read_bytes()
        write_lines(
            self.batch,
            [translation("00:00:00.000", "00:00:01.000", "Hello.", "您好。")],
        )

        with self.assertRaisesRegex(ValueError, "SHA-256|changed"):
            install_translation_batch(
                self.corrections_path,
                self.checkpoint,
                self.batch,
                replace_from=0,
                expected_translations_sha256="0" * 64,
            )

        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_replacement_can_recover_after_a_source_suffix_changes(self):
        write_lines(
            self.checkpoint,
            [
                translation("00:00:00.000", "00:00:01.000", "Hello.", "你好。"),
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We keep Python3.",
                    "我们保留 Python3。",
                ),
                translation(
                    "00:00:02.400",
                    "00:00:03.400",
                    "That is all.",
                    "以上就是全部内容。",
                ),
            ],
        )
        expected_hash = sha256(self.checkpoint)
        changed_corrections = [
            self.corrections[0],
            Correction(1200, 2200, "We retain Python3.", ()),
            self.corrections[2],
        ]
        write_corrections_atomic(self.corrections_path, changed_corrections)
        write_lines(
            self.batch,
            [
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We retain Python3.",
                    "我们保留 Python3。",
                ),
                translation(
                    "00:00:02.400",
                    "00:00:03.400",
                    "That is all.",
                    "以上就是全部内容。",
                ),
            ],
        )

        result = install_translation_batch(
            self.corrections_path,
            self.checkpoint,
            self.batch,
            replace_from=1,
            expected_translations_sha256=expected_hash,
        )

        self.assertTrue(result["complete"])
        self.assertEqual(read_translations(self.checkpoint)[1].source_text, "We retain Python3.")

    def test_reader_rejects_reordered_keys_and_invalid_text(self):
        cases = [
            {
                "start": "00:00:00.000",
                "end": "00:00:01.000",
                "text_zh": "你好。",
                "source_text": "Hello.",
            },
            translation("00:00:00.000", "00:00:01.000", "", "你好。"),
            translation("00:00:00.000", "00:00:01.000", "Hello.", "  "),
            translation("00:00:00.000", "00:00:01.000", "Hello.", "你\n好。"),
        ]

        for index, row in enumerate(cases):
            with self.subTest(index=index):
                write_lines(self.batch, [row])
                with self.assertRaises(ValueError):
                    read_translations(self.batch)

    def test_full_checkpoint_reports_complete(self):
        write_lines(
            self.batch,
            [
                translation("00:00:00.000", "00:00:01.000", "Hello.", "你好。"),
                translation(
                    "00:00:01.200",
                    "00:00:02.200",
                    "We keep Python3.",
                    "我们保留 Python3。",
                ),
                translation(
                    "00:00:02.400",
                    "00:00:03.400",
                    "That is all.",
                    "以上就是全部内容。",
                ),
            ],
        )

        result = install_translation_batch(
            self.corrections_path, self.checkpoint, self.batch
        )

        self.assertTrue(result["complete"])
        self.assertEqual(result["next_index"], 3)


if __name__ == "__main__":
    unittest.main()

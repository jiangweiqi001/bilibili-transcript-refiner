import unittest
from pathlib import Path

from scripts.runtime_layout import default_runtime_root, user_key


class RuntimeLayoutTests(unittest.TestCase):
    def test_ascii_local_app_data_keeps_private_runtime(self):
        env = {"LOCALAPPDATA": r"C:\Users\alice\AppData\Local"}
        self.assertEqual(
            default_runtime_root(env),
            Path(r"C:\Users\alice\AppData\Local\bilibili-transcript-refiner\runtime-v1"),
        )

    def test_unicode_profile_uses_ascii_public_per_user_runtime(self):
        env = {
            "LOCALAPPDATA": "C:\\Users\\\u6d4b\u8bd5\\AppData\\Local",
            "PUBLIC": r"C:\Users\Public",
        }
        self.assertEqual(user_key(env["LOCALAPPDATA"]), "7a6eeeb07d1464ab")
        self.assertEqual(
            default_runtime_root(env),
            Path(
                r"C:\Users\Public\bilibili-transcript-refiner\users"
                r"\7a6eeeb07d1464ab\runtime-v1"
            ),
        )

    def test_unicode_profile_requires_ascii_public_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "explicit ASCII --runtime-root"):
            default_runtime_root({"LOCALAPPDATA": "C:\\Users\\\u6d4b\u8bd5"})


if __name__ == "__main__":
    unittest.main()

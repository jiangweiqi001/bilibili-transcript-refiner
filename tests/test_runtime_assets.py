import json
import unittest
from pathlib import Path


class RuntimeAssetManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (Path(__file__).parents[1] / "scripts" / "runtime-assets.json").read_text(
                encoding="utf-8"
            )
        )
        cls.assets = {item["id"]: item for item in cls.manifest["assets"]}

    def test_hugging_face_assets_use_immutable_revisions(self):
        for asset_id in ("sensevoice", "vad"):
            asset = self.assets[asset_id]
            self.assertRegex(asset["revision"], r"^[0-9a-f]{40}$")
            self.assertIn(f"/resolve/{asset['revision']}/", asset["url"])
            self.assertNotEqual(asset["revision"], "main")

    def test_archives_pin_hashes_for_every_runtime_executable(self):
        expected = {
            "ffmpeg": {"ffmpeg.exe", "ffprobe.exe"},
            "funasr_avx2": {
                "llama-funasr-sensevoice.exe",
                "llama-funasr-vad.exe",
            },
        }
        for asset_id, leaves in expected.items():
            expanded = self.assets[asset_id]["expanded_files"]
            self.assertEqual({item["leaf"] for item in expanded}, leaves)
            for item in expanded:
                self.assertRegex(item["sha256"], r"^[0-9A-F]{64}$")


if __name__ == "__main__":
    unittest.main()

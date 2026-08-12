import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_transcript import prepare_transcript


class FakeRunner:
    def __init__(self, *, empty_second_segment=False):
        self.commands = []
        self.empty_second_segment = empty_second_segment

    def __call__(self, args):
        command = [str(arg) for arg in args]
        self.commands.append(command)
        executable = Path(command[0]).name.lower()

        if executable == "yt-dlp.exe" and "--dump-single-json" in command:
            url = command[-1]
            bvid = url.split("/video/")[1].split("/")[0]
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "id": bvid,
                        "title": "测试视频",
                        "uploader": "测试UP主",
                        "duration": 59.98,
                        "webpage_url": url,
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )

        if executable == "yt-dlp.exe":
            template = Path(command[command.index("-o") + 1])
            audio = Path(str(template).replace("%(ext)s", "m4a"))
            audio.parent.mkdir(parents=True, exist_ok=True)
            audio.write_bytes(b"fake-audio")
            return subprocess.CompletedProcess(
                command, 0, stdout=str(audio) + "\n", stderr=""
            )

        if executable == "ffmpeg.exe":
            destination = Path(command[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"fake-wav")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        if executable == "llama-funasr-vad.exe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="[vad] 2 segments (max_seg=30000ms)\n0 33600\n33600 59980\n",
            )

        if executable == "llama-funasr-sensevoice.exe":
            clip = Path(command[command.index("-a") + 1])
            index = int(clip.stem)
            text = "" if self.empty_second_segment and index == 1 else [
                "<|zh|><|NEUTRAL|><|Speech|>第一段",
                "<|zh|><|NEUTRAL|><|Speech|>第二段",
            ][index]
            return subprocess.CompletedProcess(
                command, 0, stdout=text + ("\n" if text else ""), stderr="[sensevoice] done\n"
            )

        raise AssertionError(f"unexpected command: {command}")


def create_runtime(root: Path) -> Path:
    tool_names = {
        "yt_dlp": "yt-dlp.exe",
        "ffmpeg": "ffmpeg.exe",
        "ffprobe": "ffprobe.exe",
        "funasr_sensevoice": "llama-funasr-sensevoice.exe",
        "funasr_vad": "llama-funasr-vad.exe",
        "sensevoice_model": "sensevoice-small-q8.gguf",
        "vad_model": "fsmn-vad.gguf",
    }
    manifest = {"schema_version": 1, "runtime_root": str(root)}
    for key, name in tool_names.items():
        path = root / "fake-runtime" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        manifest[key] = str(path)
    (root / "runtime.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return root


class PrepareTranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.runtime = create_runtime(self.base / "runtime")
        self.output = self.base / "科学大发现" / "B站逐字稿"

    def tearDown(self):
        self.temp.cleanup()

    def test_prepares_timestamped_raw_evidence(self):
        runner = FakeRunner()
        result = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=runner,
        )

        self.assertEqual(result.output_dir.name, "BV1rnGt61E4j")
        self.assertTrue(result.page_defaulted)
        self.assertEqual(
            result.raw_path.read_text(encoding="utf-8").splitlines(),
            [
                '{"start":"00:00:00.000","end":"00:00:33.600","text":"第一段"}',
                '{"start":"00:00:33.600","end":"00:00:59.980","text":"第二段"}',
            ],
        )
        self.assertEqual(result.job_manifest["state"], "asr_complete")
        self.assertTrue(result.job_dir.is_relative_to(self.runtime))
        self.assertTrue(all(ord(character) < 128 for character in str(result.job_dir)))

    def test_explicit_page_uses_suffix_and_is_not_defaulted(self):
        result = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/?p=2",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        self.assertEqual(result.output_dir.name, "BV1rnGt61E4j-p02")
        self.assertFalse(result.page_defaulted)

    def test_successful_raw_is_reused_without_running_tools(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        before = first.raw_path.read_bytes()

        def forbidden_runner(_args):
            raise AssertionError("tools must not run when evidence is reusable")

        second = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=forbidden_runner,
        )
        self.assertTrue(second.reused)
        self.assertEqual(second.raw_path.read_bytes(), before)

    def test_resume_skips_successful_segment_checkpoint(self):
        runner = FakeRunner(empty_second_segment=True)
        with self.assertRaisesRegex(ValueError, "empty ASR text"):
            prepare_transcript(
                "https://www.bilibili.com/video/BV1rnGt61E4j/",
                self.output,
                self.runtime,
                runner=runner,
            )
        self.assertFalse((self.output / "BV1rnGt61E4j" / "raw-transcript.jsonl").exists())

        resumed_runner = FakeRunner()
        result = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=resumed_runner,
        )
        sense_commands = [
            command
            for command in resumed_runner.commands
            if Path(command[0]).name.lower() == "llama-funasr-sensevoice.exe"
        ]
        self.assertEqual(len(sense_commands), 1)
        self.assertTrue(result.raw_path.exists())

    def test_explicit_rerun_archives_old_raw_outside_formal_output(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        old_bytes = first.raw_path.read_bytes()
        result = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
            rerun_asr=True,
        )
        archives = list((result.job_dir / "archive").glob("raw-transcript-*.jsonl"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), old_bytes)
        self.assertEqual(
            sorted(path.name for path in result.output_dir.iterdir()),
            ["raw-transcript.jsonl"],
        )


if __name__ == "__main__":
    unittest.main()

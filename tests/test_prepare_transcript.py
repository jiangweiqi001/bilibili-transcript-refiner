import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_transcript import _job_directory, prepare_transcript
from scripts.transcript_contract import BilibiliTarget, exclusive_job_lock


class FakeRunner:
    def __init__(
        self,
        *,
        empty_second_segment=False,
        source_duration=59.98,
        cached_source_duration=None,
        cached_wav_duration=59.98,
    ):
        self.commands = []
        self.empty_second_segment = empty_second_segment
        self.source_duration = source_duration
        self.cached_source_duration = (
            source_duration if cached_source_duration is None else cached_source_duration
        )
        self.cached_wav_duration = cached_wav_duration
        self.converted_speech = False
        self.downloaded_audio = False

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
            self.downloaded_audio = True
            return subprocess.CompletedProcess(
                command, 0, stdout=str(audio) + "\n", stderr=""
            )

        if executable == "ffmpeg.exe":
            destination = Path(command[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"fake-wav")
            if destination.name == "speech.partial.wav":
                self.converted_speech = True
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        if executable == "ffprobe.exe":
            media = Path(command[-1])
            if media.name.startswith("source."):
                duration = (
                    self.source_duration
                    if self.downloaded_audio
                    else self.cached_source_duration
                )
            else:
                duration = 59.98 if self.converted_speech else self.cached_wav_duration
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"format": {"duration": str(duration)}}),
                stderr="",
            )

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

    def test_download_uses_unique_staging_before_installing_canonical_audio(self):
        runner = FakeRunner()
        result = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=runner,
        )
        download = next(
            command
            for command in runner.commands
            if Path(command[0]).name.lower() == "yt-dlp.exe"
            and "--dump-single-json" not in command
        )
        template = Path(download[download.index("-o") + 1])
        self.assertIn("staging", template.parts)
        self.assertNotEqual(template.parent, result.job_dir)
        self.assertEqual(len(list(result.job_dir.glob("source.*"))), 1)

    def test_rebuilds_truncated_cached_wav_before_asr(self):
        job = self.runtime / "jobs" / "BV1rnGt61E4j"
        job.mkdir(parents=True, exist_ok=True)
        (job / "source.m4a").write_bytes(b"complete-source")
        (job / "speech.wav").write_bytes(b"truncated-wav")
        (job / "vad.json").write_text(
            json.dumps([{"start_ms": 0, "end_ms": 10_000}]),
            encoding="utf-8",
        )
        runner = FakeRunner(cached_wav_duration=10.0)

        prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=runner,
        )

        probes = [
            command
            for command in runner.commands
            if Path(command[0]).name.lower() == "ffprobe.exe"
        ]
        conversions = [
            command
            for command in runner.commands
            if Path(command[0]).name.lower() == "ffmpeg.exe"
            and Path(command[-1]).name == "speech.partial.wav"
        ]
        vad_runs = [
            command
            for command in runner.commands
            if Path(command[0]).name.lower() == "llama-funasr-vad.exe"
        ]
        self.assertGreaterEqual(len(probes), 2)
        self.assertEqual(len(conversions), 1)
        self.assertEqual(len(vad_runs), 1)

    def test_archives_and_redownloads_truncated_cached_source(self):
        job = _job_directory(
            self.runtime, self.output, BilibiliTarget("BV1rnGt61E4j")
        )
        job.mkdir(parents=True, exist_ok=True)
        (job / "source.m4a").write_bytes(b"truncated-source")
        runner = FakeRunner(source_duration=59.98, cached_source_duration=10.0)

        result = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=runner,
        )

        downloads = [
            command
            for command in runner.commands
            if Path(command[0]).name.lower() == "yt-dlp.exe"
            and "--dump-single-json" not in command
        ]
        self.assertEqual(len(downloads), 1)
        self.assertEqual(len(list((result.job_dir / "archive").glob("source.invalid-*.m4a"))), 1)

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

    def test_reuse_rejects_valid_jsonl_whose_sha256_changed(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        rows = [
            json.loads(line)
            for line in first.raw_path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0]["text"] = "tampered but still valid JSONL"
        first.raw_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "SHA-256"):
            prepare_transcript(
                "https://www.bilibili.com/video/BV1rnGt61E4j/",
                self.output,
                self.runtime,
                runner=lambda _args: (_ for _ in ()).throw(
                    AssertionError("tools must not run before reuse validation")
                ),
            )

    def test_reuse_requires_completed_manifest_state(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        manifest_path = first.job_dir / "job.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["state"] = "unexpected"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "not complete"):
            prepare_transcript(
                "https://www.bilibili.com/video/BV1rnGt61E4j/",
                self.output,
                self.runtime,
                runner=lambda _args: (_ for _ in ()).throw(
                    AssertionError("tools must not run before reuse validation")
                ),
            )

    def test_reuse_requires_manifest_to_name_the_same_raw_path(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        manifest_path = first.job_dir / "job.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["raw_path"] = str(self.base / "somewhere-else" / "raw-transcript.jsonl")
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "same output path"):
            prepare_transcript(
                "https://www.bilibili.com/video/BV1rnGt61E4j/",
                self.output,
                self.runtime,
                runner=lambda _args: (_ for _ in ()).throw(
                    AssertionError("tools must not run before reuse validation")
                ),
            )

    def test_reuse_requires_manifest_to_name_the_same_video(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        manifest_path = first.job_dir / "job.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bvid"] = "BV1aaaaaaaaaa"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "identity"):
            prepare_transcript(
                "https://www.bilibili.com/video/BV1rnGt61E4j/",
                self.output,
                self.runtime,
                runner=lambda _args: (_ for _ in ()).throw(
                    AssertionError("tools must not run before reuse validation")
                ),
            )

    def test_same_video_uses_distinct_jobs_for_distinct_output_roots(self):
        first_output = self.base / "out-a"
        second_output = self.base / "out-b"
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            first_output,
            self.runtime,
            runner=FakeRunner(),
        )
        second = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            second_output,
            self.runtime,
            runner=FakeRunner(),
        )
        reused_first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            first_output,
            self.runtime,
            runner=lambda _args: (_ for _ in ()).throw(
                AssertionError("tools must not run when the first job is reusable")
            ),
        )

        self.assertNotEqual(first.job_dir, second.job_dir)
        self.assertEqual(reused_first.job_dir, first.job_dir)
        self.assertEqual(
            Path(reused_first.job_manifest["raw_path"]).resolve(),
            reused_first.raw_path.resolve(),
        )

    def test_prepare_rejects_a_concurrent_run_for_the_same_job(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        with exclusive_job_lock(first.job_dir / "job.lock"):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                prepare_transcript(
                    "https://www.bilibili.com/video/BV1rnGt61E4j/",
                    self.output,
                    self.runtime,
                    runner=lambda _args: (_ for _ in ()).throw(
                        AssertionError("tools must not run before lock acquisition")
                    ),
                )

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
        corrected = first.output_dir / "corrected-transcript.md"
        corrected.write_text("old corrected transcript", encoding="utf-8")
        old_corrected = corrected.read_bytes()
        correction_state = first.job_dir / "corrections.jsonl"
        correction_state.write_text("old correction work state\n", encoding="utf-8")
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
        corrected_archives = list(
            (result.job_dir / "archive").glob("corrected-transcript-*.md")
        )
        self.assertEqual(len(corrected_archives), 1)
        self.assertEqual(corrected_archives[0].read_bytes(), old_corrected)
        correction_archives = list(
            (result.job_dir / "archive").glob("corrections-*.jsonl")
        )
        self.assertEqual(len(correction_archives), 1)
        self.assertFalse(correction_state.exists())
        self.assertEqual(
            sorted(path.name for path in result.output_dir.iterdir()),
            ["raw-transcript.jsonl"],
        )

    def test_interrupted_explicit_rerun_resumes_same_run(self):
        first = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=FakeRunner(),
        )
        with self.assertRaisesRegex(ValueError, "empty ASR text"):
            prepare_transcript(
                "https://www.bilibili.com/video/BV1rnGt61E4j/",
                self.output,
                self.runtime,
                runner=FakeRunner(empty_second_segment=True),
                rerun_asr=True,
            )
        interrupted = json.loads(
            (first.job_dir / "job.json").read_text(encoding="utf-8")
        )

        runner = FakeRunner()
        completed = prepare_transcript(
            "https://www.bilibili.com/video/BV1rnGt61E4j/",
            self.output,
            self.runtime,
            runner=runner,
            rerun_asr=True,
        )
        sense_commands = [
            command
            for command in runner.commands
            if Path(command[0]).name.lower() == "llama-funasr-sensevoice.exe"
        ]
        self.assertEqual(completed.job_manifest["active_run"], interrupted["active_run"])
        self.assertEqual(len(sense_commands), 1)


if __name__ == "__main__":
    unittest.main()

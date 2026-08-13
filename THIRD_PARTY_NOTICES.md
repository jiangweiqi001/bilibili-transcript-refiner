# Third-party notices

The repository's own source and documentation are licensed under the MIT License in [`LICENSE`](LICENSE). The bootstrap script downloads the components below directly from their upstream release locations. They are not redistributed in this repository and remain subject to their own licenses and notices.

| Component downloaded at runtime | Pinned source | Upstream license information |
|---|---|---|
| `yt-dlp.exe` | [yt-dlp release](https://github.com/yt-dlp/yt-dlp/releases) | The yt-dlp source is Unlicense. The upstream project states that its PyInstaller executables include GPLv3+ code and the combined executable is GPLv3+. See [yt-dlp licensing](https://github.com/yt-dlp/yt-dlp#licensing) and the notices shipped inside its release. |
| FFmpeg `ffmpeg.exe` and `ffprobe.exe` | [Gyan Windows build](https://www.gyan.dev/ffmpeg/builds/) | Gyan states that its static Windows builds are GPLv3. FFmpeg's exact license depends on build configuration; see the [FFmpeg license](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md). |
| FunASR `llama-funasr-sensevoice.exe` and `llama-funasr-vad.exe` | [modelscope/FunASR release](https://github.com/modelscope/FunASR/releases) | MIT License. See the [FunASR license](https://github.com/modelscope/FunASR/blob/main/LICENSE). |
| SenseVoiceSmall-GGUF `sensevoice-small-q8.gguf` | [FunAudioLLM/SenseVoiceSmall-GGUF](https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF) | Apache License 2.0 according to the pinned Hugging Face model card. |
| fsmn-vad-GGUF `fsmn-vad.gguf` | [FunAudioLLM/fsmn-vad-GGUF](https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF) | Apache License 2.0 according to the pinned Hugging Face model card. |

Exact versions, immutable revisions, URLs, sizes, archive hashes, and expanded executable hashes are recorded in [`scripts/runtime-assets.json`](scripts/runtime-assets.json). Users who redistribute downloaded binaries or models must review and comply with the complete upstream terms; this notice is not a replacement for those terms.

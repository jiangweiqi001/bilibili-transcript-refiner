# Bilibili Transcript Refiner

把一个完整的 B 站 BV 视频链接转换成可追溯的原始识别稿和严格忠实校订稿。

## 功能

- 使用本地 SenseVoiceSmall 将视频音轨转成带全局时间戳的原始识别证据。
- 由 Codex 结合上下文校订明显的识别错误、术语、人名、断句和标点。
- 最终固定输出 `raw-transcript.jsonl` 和 `corrected-transcript.md`。

## 运行要求

- Windows 10/11 x64。
- Python 3.11+ 和 PowerShell 5.1+。
- CPU 支持 AVX2、FMA、F16C 和 BMI2。
- 首次安装可访问 GitHub、Hugging Face 和 Bilibili。

不需要预装 yt-dlp、FFmpeg、FunASR 或语音模型。首次运行会自动下载五个固定版本且经过 SHA-256 校验的依赖，传输约 372 MiB；安装后约占 700 MiB，尚不包含后续视频任务文件。

## 安装

可以让 Codex 使用 `$skill-installer` 从以下 GitHub 仓库安装：

```text
https://github.com/jiangweiqi001/bilibili-transcript-refiner
```

也可以直接克隆到 Codex 的个人 Skill 目录：

```powershell
git clone https://github.com/jiangweiqi001/bilibili-transcript-refiner "$HOME/.agents/skills/bilibili-transcript-refiner"
```

## 首次运行

直接在 Codex 中调用 Skill；它会先执行引导脚本并自动准备工具与模型：

```text
请使用 $bilibili-transcript-refiner 处理 https://www.bilibili.com/video/BV1xxxxxxxxx/，输出到 D:\B站逐字稿。
```

需要单独检查或预装运行时，也可以从任意工作目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap_runtime.ps1"
```

## 中文 Windows 用户名

FunASR 运行路径必须为 ASCII。若 `%LOCALAPPDATA%` 含中文或其他非 ASCII 字符，脚本会自动切换到 `%PUBLIC%\bilibili-transcript-refiner\users\<user-key>\runtime-v1`，不同用户之间不会共享可写任务目录。若公共目录也不可用，按报错提示显式传入 ASCII 路径，例如 `-RuntimeRoot C:\btr-runtime`。

## 忠实性原则

- 严格忠实：不润色、不概括、不把口语改写成书面语。
- 可追溯：保留不可变原始识别稿、逐段时间戳和校订结果。
- 不猜测：无法确认时使用 `[疑似：候选词]` 或 `[听不清]`。
- 可恢复：支持断点续跑、哈希校验、任务隔离和并发防覆盖。

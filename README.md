点点关注谢谢喵

# Bilibili Transcript Refiner

> 给我一个完整的 B 站 BV 视频链接，还你一份带时间戳、可追溯、严格忠实的逐字稿。

[![test](https://github.com/jiangweiqi001/bilibili-transcript-refiner/actions/workflows/test.yml/badge.svg)](https://github.com/jiangweiqi001/bilibili-transcript-refiner/actions/workflows/test.yml)
![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11%20x64-0078D4)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)

`Bilibili Transcript Refiner` 是一个面向 Codex 的 B 站逐字稿 Skill。它自动完成视频音轨获取、本地语音识别、上下文校订、时间戳保留和结果校验，最终交付原始识别证据与忠实校订稿。

它不是摘要器，也不是“把口语润色成文章”的改写工具。它关注的是：视频里到底说了什么，哪些地方可以确定，哪些地方仍然存疑。

## 为什么需要它

直接使用通用 ASR，常见结果是术语、人名和断句错误；直接让 AI 改写，又容易把原话悄悄变成更流畅但不再忠实的文字。长视频靠人工从头校对，则耗时且难以复核。

这个项目把三件事组合在一起：

- 用 SenseVoiceSmall 生成带全局时间戳的原始识别证据。
- 用 Codex 结合上下文校订明确错误，同时禁止润色、概括和擅自补写。
- 用固定输出契约、哈希和最终校验保留可追溯性。

## 功能

- **完整 BV 链接直接处理**：识别 `bilibili.com/video/BV...`，支持通过 `p=` 指定分 P。
- **本地媒体处理与 ASR**：使用 yt-dlp、FFmpeg、FSMN-VAD 和 SenseVoiceSmall 完成音频准备、分段与识别。
- **全局时间戳**：每段原始文字都保留 `HH:MM:SS.mmm` 起止时间。
- **严格忠实校订**：只修正明确的识别错误、术语、人名、断句和标点，不把口语改写成书面语。
- **显式表达不确定性**：使用 `[疑似：候选词]` 和 `[听不清]`，不靠猜测填空。
- **原始证据不可变**：成功生成的 `raw-transcript.jsonl` 不会为了迎合校订结果而被覆盖。
- **断点续跑**：下载、转码、VAD、ASR 和校订都有可恢复状态，长视频中断后无需全部重来。
- **安全完成检查**：只有原始哈希、逐段对应关系、时间戳和存疑项全部通过校验，才会生成正式校订稿。

校订规则不是隐藏提示词：可以直接查看 [`references/faithful-correction.md`](references/faithful-correction.md) 和 [`references/output-contract.md`](references/output-contract.md)。依赖版本、下载地址、文件大小与 SHA-256 则集中记录在 [`scripts/runtime-assets.json`](scripts/runtime-assets.json)。

关键机制也有对应的自动化测试：[`tests/test_prepare_transcript.py`](tests/test_prepare_transcript.py) 覆盖任务隔离、缓存校验、断点恢复和原始证据复用，[`tests/test_finalize_transcript.py`](tests/test_finalize_transcript.py) 覆盖原始哈希、逐段对应、并发保护和正式目录约束。

## 忠实性边界

“校订”不等于“改写”。这个 Skill 可以修正上下文能够明确判断的同音字、专业术语、人名、断句和标点，但不会为了让内容显得更专业而重写说话人的表达。

- 说话人重复、犹豫或使用口语时，原则上保留。
- 视频中的观点即使可能有事实错误，也不会被悄悄替换成“正确答案”。
- 上下文只能提供候选词而不能确认时，写成 `[疑似：候选词]`。
- 音频不足以支持可靠判断时，写成 `[听不清]`，不强行补齐一句看似通顺的话。

换句话说：目标不是得到最漂亮的文章，而是得到最接近原始表达、同时方便复核的文字证据。

## 项目亮点

| 亮点 | 带来的价值 |
|---|---|
| 原始稿与校订稿并存 | 可以随时回看 AI 改了什么 |
| 一行原始记录对应一行校订状态 | 不容易漏段、乱序或悄悄删句 |
| ASR 在本地运行 | 音频处理和语音识别不依赖云端 ASR 服务 |
| 自动准备运行环境 | 用户不需要预装 yt-dlp、FFmpeg、FunASR 或模型 |
| 所有资产固定版本并校验 SHA-256 | 降低下载漂移或文件损坏带来的不确定性 |
| 中文 Windows 用户名兼容 | 自动选择按用户隔离的 ASCII 运行路径 |
| 正式目录只有两个文件 | 模型、音频、日志和中间状态不会污染交付目录 |
| 每周检查远端资产元数据 | 上游文件变化会在 GitHub Actions 中暴露 |

## 工作流程

```text
完整 B 站 BV 链接
        |
        v
yt-dlp -> FFmpeg -> FSMN-VAD -> SenseVoiceSmall
        |                         |
        |                         +--> 带时间戳的原始 ASR 证据
        v
Codex 按上下文逐段忠实校订
        |
        v
哈希、行数、时间戳、存疑标记与目录结构校验
        |
        v
raw-transcript.jsonl + corrected-transcript.md
```

媒体准备和 ASR 在本地执行；Codex 负责上下文校订。因此项目不会把“整个流程”宣传成完全离线。

## 适用场景

- 技术演讲、课程和教程的可检索文字版。
- 访谈、播客、直播回放和口述材料整理。
- 论文调研、事实核对和需要回到原视频时间点的引用。
- 为字幕制作准备带时间戳的原始底稿。
- 希望保留口头表达，而不是只要摘要或文章化改写的内容。

## 快速开始

### 方法一：让 Codex 安装

在 Codex 中告诉 `$skill-installer` 从这个仓库安装：

```text
请使用 $skill-installer 安装：
https://github.com/jiangweiqi001/bilibili-transcript-refiner
```

这是最省事的方式，适合希望由 Codex 完成 Skill 安装的人。

### 方法二：手动克隆

```powershell
git clone https://github.com/jiangweiqi001/bilibili-transcript-refiner "$HOME/.agents/skills/bilibili-transcript-refiner"
```

手动克隆适合希望明确控制安装目录，并用 `git pull` 自行更新的人。

安装后重新打开一个 Codex 任务，让新 Skill 被发现。

## 首次运行

```text
请使用 $bilibili-transcript-refiner 处理：
https://www.bilibili.com/video/BV1GJ411x7h7/?p=1
输出到 D:\B站逐字稿
```

Codex 会运行完整流程。第一次使用时，引导脚本会自动下载并校验所需工具与模型。

如果想提前准备或检查运行环境，可以从任意工作目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap_runtime.ps1"
```

## 使用示例

下面的文字仅用于展示文件格式，不代表特定视频的真实转写结果。

### 原始识别证据

`raw-transcript.jsonl` 每行都是一个不可变的识别片段：

```json
{"start":"00:00:12.400","end":"00:00:18.720","text":"今天我们来聊一下与音识别。"}
```

### 忠实校订结果

`corrected-transcript.md` 保留时间点、校订文本和存疑汇总：

```markdown
## 逐字稿

[00:00:12.400] 今天我们来聊一下语音识别。

[00:01:42.000] 这里需要一个[疑似：遍历性]条件。

## 存疑处

- [00:01:42.000] `[疑似：遍历性]`：也可能是其他术语，音频不足以确认。
```

## 输出内容

每个视频或分 P 的正式目录严格只保留两个文件：

```text
<输出目录>/
└── BV1GJ411x7h7/
    ├── raw-transcript.jsonl       # 原始 ASR 证据，不可变
    └── corrected-transcript.md    # 忠实校订后的可读逐字稿
```

音频、WAV、模型、日志、检查点和任务状态都保存在运行时目录，不会混入正式交付目录。

## 运行要求

- Windows 10/11 x64。
- Python 3.11+。
- PowerShell 5.1+。
- CPU 支持 AVX2、FMA、F16C 和 BMI2。
- 首次安装时能够访问 GitHub 和 Hugging Face；处理视频时能够访问 Bilibili。

不需要预装音频转文字模型。首次运行会自动下载五个经过 SHA-256 校验的固定依赖，传输约 372 MiB，安装后约占 700 MiB；视频、音频和任务缓存不包含在这个数字内。

### 中文 Windows 用户名

FunASR 要求运行路径只包含 ASCII。若 `%LOCALAPPDATA%` 含中文或其他非 ASCII 字符，脚本会自动使用：

```text
%PUBLIC%\bilibili-transcript-refiner\users\<user-key>\runtime-v1
```

如果公共路径也不可用，报错会提示显式传入 ASCII 路径，例如 `-RuntimeRoot C:\btr-runtime`。

## URL 与视频边界

- 必须提供完整的 `bilibili.com/video/BV...` 地址。
- 不直接接受 `b23.tv` 或 `bili2233.cn` 短链接，请先展开成完整 BV 地址。
- one video/page per invocation：每次处理一个视频页面；带 `p=` 时处理指定分 P，否则处理第 1 P。
- 登录可见、付费、地区限制、已删除或触发 B 站风控的视频仍可能失败。
- 这不是播放列表批量下载工具。

## 常见问题

### 别人的电脑没有语音模型，能运行吗？

可以。引导脚本会自动下载固定版本的 SenseVoiceSmall、FSMN-VAD、FunASR、FFmpeg 和 yt-dlp，并逐个检查 SHA-256。用户只需满足 Windows、Python、PowerShell、CPU 和网络要求。

### 为什么同时保留原始稿和校订稿？

原始稿回答“模型最初识别成了什么”，校订稿回答“结合上下文后，更可靠的忠实文本是什么”。两者分开，才方便复核修改、定位时间点和发现 AI 是否改得过头。

### 是完全离线的吗？

不是。媒体下载、依赖下载和 Codex 校订需要相应网络能力；音频转换、VAD 和 SenseVoiceSmall ASR 在本地运行。校订阶段会把逐字稿内容交给当前 Codex 环境处理，具体数据保留方式取决于你所使用的 Codex 产品、账户和组织设置。

### 一小时视频要多久，会消耗多少 Codex token？

目前没有足够跨硬件、跨视频类型的数据给出可信的统一基准。耗时受下载速度、CPU、视频时长、VAD 分段数量和校订复杂度影响；Codex token 消耗也会随逐字稿长度与疑难段数量变化。README 不用单台电脑的结果冒充普遍性能。

### 准确率是多少？

目前没有覆盖不同口音、录音质量和专业领域的人工标注测试集，因此不提供一个看似精确但无法泛化的准确率数字。建议先用一段你熟悉的公开视频试跑，抽查原始稿、校订稿和对应时间点，再决定它是否适合你的材料。涉及法律、医疗、财务或敏感访谈时，应由领域人员复核，不能把 AI 校订当作权威记录。

### 能保证所有 B 站视频都成功吗？

不能。B 站登录状态、地区限制、付费权限、视频删除和反滥用策略都可能影响下载。项目会保留任务状态并给出失败信息，但不会绕过访问权限。

### 支持 macOS、Linux 或老 CPU 吗？

当前公开版本只验证 Windows 10/11 x64，并要求 AVX2、FMA、F16C 和 BMI2。其他平台与非 AVX2 CPU 暂不在支持范围内。

### 如何清理模型和任务缓存？

正式交付文件只在你指定的输出目录中。确认没有转写任务运行后，可以在资源管理器中查看并清理运行根目录；默认是 `%LOCALAPPDATA%\bilibili-transcript-refiner\runtime-v1`，中文用户目录则使用上文的 `%PUBLIC%` 回退路径。清理模型后，下次运行会重新下载约 372 MiB 依赖。

## 验证状态

截至 2026-08-13，这个版本已经完成：

- 44 项 Python 自动化测试。
- Windows PowerShell 路径一致性与静态契约测试。
- 五个远端运行资产的大小和摘要核验，并加入每周 GitHub Actions。
- 从空目录完成约 372 MiB 依赖下载、展开、启动检查和 `VerifyOnly` 复验。
- 从 Skill 仓库之外处理真实 BV 视频，在中文输出路径成功生成 46 行原始逐字稿。

这些数字用于说明发布时实际做过哪些验收，不代表所有视频都会产生相同行数或耗时。

## 支持与分享

如果这个项目帮你省下了听写和校对时间：

- 给仓库点一个 **Star**，方便以后找到。
- 分享给同样需要 B 站逐字稿、课程整理或访谈转写的人。
- 遇到可复现问题，请提交 [GitHub Issue](https://github.com/jiangweiqi001/bilibili-transcript-refiner/issues)，附上 Windows 版本、Python 版本、完整 BV 链接和报错信息。

项目地址：<https://github.com/jiangweiqi001/bilibili-transcript-refiner>

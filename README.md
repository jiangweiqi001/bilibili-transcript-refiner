# Bilibili Transcript Refiner

把一个完整的 B 站 BV 视频链接转换成可追溯的原始识别稿和严格忠实校订稿。

## 功能

- 使用本地 SenseVoiceSmall 将视频音轨转成带全局时间戳的原始识别证据。
- 由 Codex 结合上下文校订明显的识别错误、术语、人名、断句和标点。
- 最终固定输出 `raw-transcript.jsonl` 和 `corrected-transcript.md`。

## 亮点

- 严格忠实：不润色、不概括、不把口语改写成书面语。
- 可追溯：保留不可变原始识别稿、逐段时间戳和校订结果。
- 不猜测：无法确认时使用 `[疑似：候选词]` 或 `[听不清]`。
- 可恢复：支持断点续跑、哈希校验、任务隔离和并发防覆盖。

## 使用示例

```text
请使用 $bilibili-transcript-refiner 处理 https://www.bilibili.com/video/BV1xxxxxxxxx/，输出到 D:\B站逐字稿。
```

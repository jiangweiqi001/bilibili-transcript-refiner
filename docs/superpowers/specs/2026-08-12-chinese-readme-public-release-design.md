# 中文 README 与公开发布设计

## 目标

为 `bilibili-transcript-refiner` 增加一份极简中文 `README.md`，并在验证通过后将 GitHub 仓库从私有改为公开。

## README 内容

README 只包含以下主体内容：

1. **功能**：说明 Skill 接收完整 Bilibili BV 视频链接，先由本地 SenseVoiceSmall 生成带时间戳的原始识别证据，再由 Codex 按严格忠实模式校订，最终固定输出两个文件。
2. **亮点**：突出不润色、不概括、不书面化；保留不可变原始证据和时间戳；显式标记疑似词与听不清；支持断点续跑和防覆盖。
3. **使用示例**：给出一条包含 `$bilibili-transcript-refiner`、完整 `bilibili.com/video/BV...` 链接和输出目录的自然语言示例。

除标题和一句定位说明外，不增加安装教程、实现原理、故障排查、变更记录或长篇背景。

## 仓库与验证

- 更新静态契约：允许根目录存在 `README.md`，并检查三个中文章节与关键功能表述。
- 保持 `SKILL.md`、脚本、固定输出契约和运行逻辑不变。
- 运行全部 Python 测试、静态契约、Skill 包校验和差异检查。
- 提交并推送 `main`，将 `jiangweiqi001/bilibili-transcript-refiner` 改为公开仓库，等待远端 Windows CI 通过。

## 完成标准

公开仓库根目录可直接看到极简中文 README；README 不夸大能力，测试与 CI 全部通过，本地和远端提交一致。

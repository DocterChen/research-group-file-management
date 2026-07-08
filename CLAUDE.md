# 文献管理 - Claude Code 项目指令

## 核心指令

@./AGENTS.md

## Claude Code 特定说明

- `AGENTS.md` 是通用指令源；本文件只补充 Claude Code 适配
- 引用文件用 Markdown 链接，必要时带行号：`[file.md:42](path/file.md#L42)`
- 复杂任务用 TodoWrite；改代码前先读文件，优先精确编辑
- 避免无关重构；修改 `AGENTS.md` 后更新 `CHANGELOG.md`
- 与 `AGENTS.md` 保持一致：涉及 UI、权限、抓取、认证和数据流时，优先测试先行并完成运行验证
- 与 `AGENTS.md` 保持一致：当用户明确要求整包规则时，必须执行 `awesome-code` 门禁流程、自主决策不追问，并在交付前完成可运行验证
- 与 `AGENTS.md` 保持一致：当用户要求把该整包规则写入 `AGENTS.md` 时，必须同步检查 `CLAUDE.md` 核心约束并更新 `CHANGELOG.md`

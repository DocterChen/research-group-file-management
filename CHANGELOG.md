# Changelog

本文件记录项目重要变更，格式遵循 Keep a Changelog，并优先维护 `[Unreleased]`。

## [Unreleased]

### Added（新增）

- 新增本地浏览器 UI：提供登录页、工作台仪表盘、成员/项目/成果列表、成果详情页与提交/审核操作。
- 新增本地认证存储与会话机制：支持首次启动创建管理员账号，并通过 HTTP cookie 保持登录状态。
- 新增 `litman web serve` 入口，允许直接从 CLI 启动浏览器界面。
- 新增 `AGENTS.md` 交互偏好：默认优先 UI / 可视化交付，并在复杂任务中遵循 `awesome-code` 协作规范。

- 新增科研成果管理 MVP：统一 `ResearchOutput`、`Member`、`Project`、`ReviewRecord`、`AuditLog` 数据模型，覆盖文章、专利、软著、会议成果、项目材料和数据代码类型。
- 新增角色权限与审核流：支持 `pi` / `admin` / `member` / `readonly` 角色，落地 `draft -> submitted -> approved` 审核闭环。
- 新增本地多实体 JSON 存储：默认在 `data/local/` 下维护 `members.json`、`projects.json`、`outputs.json`、`reviews.json` 和 `audit_logs.json`。
- 新增 CLI 命令组：`members`、`projects`、`outputs`、`stats summary`、`export csv`。
- 新增产品文档 `docs/product/REQUIREMENTS.md`、`docs/product/PERMISSION_MATRIX.md`、`docs/product/ENTITY_FIELDS.md`。
- 新增科研成果回归测试 `tests/test_research_manager.py`，覆盖模型、权限、审核流、导出和 CLI 主路径。
- 新增多实体虚构示例 `examples/research_outputs.sample.json`。

### Changed（变更）

- 将项目定位从“文献管理 CLI 原型”升级为“课题组科研成果与相关文件管理 CLI MVP”。
- 调整 `.gitignore`，允许提交 `tests/` 回归测试目录，便于 GitHub 发布时保留测试资产。
- 重写 [README.md](/Users/chenhang/Documents/Codex/文献管理/README.md) 快速开始、目录结构和数据边界说明，使其匹配新的成果管理工作流。
- 更新 [docs/plans/PROJECT_ROADMAP.md](/Users/chenhang/Documents/Codex/文献管理/docs/plans/PROJECT_ROADMAP.md)，将路线图改为围绕统一成果模型、权限、附件和 Web 迁移展开。
- 包版本从 `0.2.0` 提升为 `0.3.0`。

### Fixed（修复）

- 修复旧版单一文献模型无法表达项目、角色权限、审核记录和跨成果类型管理的问题。
- 修复旧版 CLI 只能处理 `add` / `list` / `show` 文献命令，无法支持科研成果提交流程的问题。

## [1.0.0] - 2026-06-23

### Added（新增）

- 初始化 AI 项目指令文件：生成 `AGENTS.md`、`CLAUDE.md`、`README.md` 与 `.gitignore`
- 配置项目工程原则、工作流和变更记录规范
- 创建 `docs/` 与 `docs/plans/` 文档目录
- 本次初始化因当前 Python 版本低于 BAC 要求，已显式关闭 BAC 自动安装与账本初始化

### Changed（变更）

### Fixed（修复）

---

## 记录规则

- 必须记录影响项目行为、结构、工作流、工程原则、指令文件或关键配置的变更
- 记录应说明改了什么、为什么改，以及影响范围
- 版本号遵循 SemVer：bug fix 递增修订号，新功能递增次版本号，破坏性变更递增主版本号

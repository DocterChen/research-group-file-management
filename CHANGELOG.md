# Changelog

本文件记录项目重要变更，格式遵循 Keep a Changelog，并优先维护 `[Unreleased]`。

## [Unreleased]

### Added（新增）

- **完整Web UI管理界面**：实现成员、项目、成果的完整CRUD操作（添加、编辑、删除）
  - 成员管理：添加/编辑/删除成员，支持角色选择和邮箱配置
  - 项目管理：添加/编辑/删除项目，支持多负责人选择和资助来源
  - 成果管理：添加/编辑/删除成果，支持文章类型动态表单
  - 引用完整性检查：删除前自动检查成员/项目是否被成果引用
  - 表单验证和友好错误提示

- **Excel高级格式导出**：使用openpyxl实现专业Excel报告
  - 汇总统计工作表：基础统计、类型分布、状态分布
  - 成果清单工作表：包含所有成果字段、样式格式化、自动筛选
  - 成员清单工作表：完整成员信息
  - 项目清单工作表：项目详情和资助信息
  - CLI命令：`export excel --output <path>`
  - Web UI导出：仪表盘”导出Excel”按钮

- **外部数据自动抓取**：支持DOI和PubMed数据库
  - DOI抓取：通过CrossRef API自动填充文章信息（标题、作者、期刊、年份等）
  - PubMed抓取：通过NCBI E-utilities API获取文章元数据
  - 新增模块：`src/lab_literature_manager/data_fetcher.py`
  - 支持命令行和编程接口调用

- **全面中文化**：所有界面文本改为简体中文
  - 登录页面、设置页面完全中文化
  - 仪表盘、成员、项目、成果页面中文化
  - 表单标签、按钮、错误提示中文化
  - 图表标题和统计标签中文化

- **Repository层完整CRUD方法**：
  - `update_member()`, `delete_member()`: 成员更新和删除
  - `update_project()`, `delete_project()`: 项目更新和删除
  - `update_output()`, `delete_output()`: 成果更新和删除（带权限检查）
  - 引用完整性检查：防止删除被引用的成员/项目

- 更新 `AGENTS.md` 代码优化规则：明确要求使用awesome-code规范、自主决策、确保程序完美运行
- 新增依赖：openpyxl（Excel导出）、PyJWT（认证增强）、requests（数据抓取）

### Changed（变更）

- Web UI导航标签全部中文化：Dashboard→仪表盘、Members→成员管理、Projects→项目管理、Outputs→成果管理
- 成员、项目、成果列表页面添加”添加”按钮，方便快速创建
- 仪表盘添加”导出Excel”按钮，一键生成完整报告
- CLI导出命令提示信息改为中文
- 优化表单样式，统一使用项目设计系统

### Fixed（修复）

- 修复Excel导出中Project模型缺少notes字段导致的AttributeError
- 修复Web UI中缺少ArticleMetadata导入的bug
- 修复表单提交后的重定向逻辑
- 修复删除操作的权限检查

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

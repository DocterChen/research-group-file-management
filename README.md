# 文献管理

课题组科研成果与相关文件管理程序，用于集中管理文章、专利、软著、会议成果、项目材料以及后续可扩展的数据/代码支撑文件。

当前版本提供本地 Python CLI 与浏览器 UI 两种入口，重点验证统一成果模型、成员/项目关系、权限判断、审核流、统计汇总、CSV 导出与可视化管理台。它适合作为课题组内部业务模型原型。

## 功能特性

- **统一成果模型**：`ResearchOutput` 覆盖文章、专利、软著、会议成果、项目材料与数据代码类型。
- **文章专属字段**：支持文章类型、期刊、DOI、PMID、分区、投稿状态等元数据。
- **成员与项目管理**：本地维护成员与项目实体，成果可关联负责人、参与人和项目。
- **权限与审核流**：支持 `pi` / `admin` / `member` / `readonly` 角色与 `draft -> submitted -> approved` 闭环。
- **完整Web UI管理**：成员、项目、成果的添加、编辑、删除全流程操作，支持表单验证和引用完整性检查。
- **Excel高级导出**：生成格式化的Excel报告，包含汇总统计、成果清单、成员清单、项目清单四个工作表。
- **外部数据抓取**：通过DOI（CrossRef）和PubMed自动填充文章元数据。
- **全面中文化**：所有界面文本使用简体中文，包括登录页、仪表盘、表单和错误提示。
- **JSON 本地存储**：默认写入 `data/local/` 下的多实体文件，并带 `schema_version`。
- **统计与导出**：支持成果汇总统计和 CSV/Excel 导出。
- **回归测试**：覆盖模型校验、权限规则、审核流、CLI 主路径与导出行为。

## 快速开始

### 环境要求

- Python 3.9+
- 推荐依赖（功能增强）：
  - `openpyxl`：Excel高级格式导出
  - `requests`：外部数据库抓取（DOI、PubMed）
  - `PyJWT`：JWT认证支持（可选）

### 运行 CLI

未安装包时，在项目根目录通过 `PYTHONPATH=src` 运行：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli --help
```

添加成员：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  members add \
  --id alice \
  --name "Alice Zhang" \
  --role member
```

添加项目：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  projects add \
  --id proj-2026-gut \
  --name "Gut Microbiome Cohort" \
  --type funding \
  --owner alice
```

添加文章成果：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  outputs add \
  --id article-001 \
  --title "Gut Microbiome Atlas for Clinical Research" \
  --type article \
  --owner alice \
  --project proj-2026-gut \
  --year 2026 \
  --article-type review \
  --journal "Journal of Example Translational Medicine" \
  --doi 10.0000/example.2026.001 \
  --submission-status writing
```

提交并审核：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  outputs submit article-001 --actor-id alice --actor-role member
```

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  members add --id pi-1 --name "Prof. Li" --role pi
```

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  outputs approve article-001 --actor-id pi-1 --actor-role pi
```

查看统计与导出：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  stats summary
```

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  export csv --output /tmp/research-output-demo/outputs.csv
```

导出Excel报告（包含格式化和多工作表）：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  --data-dir /tmp/research-output-demo \
  export excel --output /tmp/research-output-demo/report.xlsx
```

### 运行 Web UI

启动本地浏览器界面：

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli web serve
```

默认会在 `http://127.0.0.1:8080` 提供登录页，首次启动时会自动创建一个本地管理员账号：

- 用户名：`admin`
- 密码：`ChangeMe123`

登录后可查看仪表盘、成员、项目、成果列表和单条成果详情，并在页面上提交/审核成果。

### 运行测试

```bash
python3 -m unittest tests/test_research_manager.py
python3 -m unittest tests.test_web_ui
python3 -m json.tool examples/research_outputs.sample.json >/dev/null
```

## 数据目录

本地原型默认使用以下文件：

```text
data/local/
├── members.json
├── projects.json
├── outputs.json
├── reviews.json
└── audit_logs.json
```

每个文件都包含：

- `schema_version`
- `items`

## 目录结构

```text
文献管理/
├── src/lab_literature_manager/   # 统一成果模型、权限、存储、CLI
├── tests/                        # 回归测试
├── examples/                     # 可提交的虚构示例数据
├── docs/
│   ├── plans/                    # 计划与路线图
│   └── product/                  # 需求、权限矩阵、实体字段说明
├── data/local/                   # 本地真实数据，默认被 Git 忽略
├── AGENTS.md
├── CLAUDE.md
├── CHANGELOG.md
└── pyproject.toml
```

## 数据与隐私边界

- `data/local/`、`pdfs/`、`attachments/`、`exports/` 默认不提交。
- 不提交真实课题组 PDF、证书、私密笔记、本地绝对路径、成员隐私信息或未脱敏协作记录。
- `examples/` 只保存虚构数据或已脱敏公开结构样例。
- 当前版本只管理附件元数据与成果关系，不处理真实附件上传。

## 开发路线

见 [docs/plans/PROJECT_ROADMAP.md](/Users/chenhang/Documents/Codex/文献管理/docs/plans/PROJECT_ROADMAP.md) 与 [docs/plans/init-20260623.md](/Users/chenhang/Documents/Codex/文献管理/docs/plans/init-20260623.md)。

当前优先级：

1. 稳定统一成果模型和审核流。
2. 扩展更多成果类型专属字段与附件元数据。
3. 增加 `return` / `archive` / `request-delete` 等状态命令。
4. 评估 SQLite / Web 化迁移路径。

## AI 辅助开发

- Claude Code 使用 [CLAUDE.md](/Users/chenhang/Documents/Codex/文献管理/CLAUDE.md)。
- Codex CLI 使用 [AGENTS.md](/Users/chenhang/Documents/Codex/文献管理/AGENTS.md)。
- 影响项目行为、结构、工作流、工程原则或关键配置的变更必须更新 [CHANGELOG.md](/Users/chenhang/Documents/Codex/文献管理/CHANGELOG.md)。

## 许可证

MIT License

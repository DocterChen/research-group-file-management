# 科研成果管理软件 - 使用手册

## 目录

- [系统简介](#系统简介)
- [系统安装](#系统安装)
- [快速开始](#快速开始)
- [用户角色与权限](#用户角色与权限)
- [Web界面使用指南](#web界面使用指南)
- [命令行工具使用指南](#命令行工具使用指南)
- [常见问题](#常见问题)
- [故障排除](#故障排除)

---

## 系统简介

科研成果管理软件（Research Output Manager）是一款专为科研课题组设计的成果信息管理工具，帮助课题组高效管理论文、专利、软件著作权、会议成果、项目材料以及数据代码等科研资产。

### 核心功能

- **统一成果模型**：支持6大成果类型的统一管理
- **成员与项目管理**：维护课题组成员和项目信息
- **权限与审核流**：4级角色权限 + 5状态审核流程
- **外部数据抓取**：支持DOI、PubMed自动填充元数据
- **统计与导出**：成果统计、CSV/Excel导出
- **全中文界面**：完全本地化的用户体验

### 适用对象

- 课题组PI（Principal Investigator）
- 课题组管理员
- 课题组成员
- 科研秘书/助理

---

## 系统安装

### 环境要求

- **操作系统**：Windows 10+、macOS 10.15+、Linux
- **Python版本**：Python 3.9 或更高版本
- **硬盘空间**：至少100MB可用空间
- **内存**：建议2GB以上

### 安装步骤

#### 1. 检查Python版本

```bash
python3 --version
```

确保版本为 3.9 或更高。

#### 2. 获取系统代码

```bash
# 如果通过Git获取
git clone <repository-url>
cd research-group-file-management

# 或直接解压下载的压缩包
unzip research-group-file-management.zip
cd research-group-file-management
```

#### 3. 安装依赖（可选但推荐）

```bash
# 安装Excel导出支持
pip3 install openpyxl

# 安装外部数据抓取支持
pip3 install requests

# 安装JWT认证支持
pip3 install PyJWT
```

> **注意**：即使不安装这些依赖，系统仍可正常运行，但部分高级功能会受限。

#### 4. 验证安装

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli --help
```

如果看到帮助信息，说明安装成功。

---

## 快速开始

### 启动Web界面（推荐）

1. **启动服务**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli web serve
```

2. **访问系统**

打开浏览器访问：`http://127.0.0.1:8080`

3. **首次登录**

系统会自动创建默认管理员账号：

- **用户名**：`admin`
- **密码**：`ChangeMe123`

> **重要提示**：首次登录后请立即修改密码！

4. **开始使用**

登录后即可看到仪表盘，开始添加成员、项目和成果信息。

---

## 用户角色与权限

系统采用基于角色的访问控制（RBAC），定义了4种用户角色：

### 角色说明

| 角色 | 代码 | 权限范围 |
|------|------|----------|
| **PI** | `pi` | 最高权限：审核成果、管理所有数据、删除任意记录 |
| **管理员** | `admin` | 管理权限：添加/编辑成员和项目、管理成果（不能审核） |
| **成员** | `member` | 基础权限：创建和编辑自己的成果、查看所有成果 |
| **只读** | `readonly` | 查看权限：仅能查看已通过审核的成果 |

### 成果状态与权限

成果在系统中有5种状态：

```
草稿 → 待审核 → 已退回/已通过 → 已归档
```

| 操作 | PI | 管理员 | 成员 | 只读 |
|------|:--:|:------:|:----:|:----:|
| 查看草稿 | ✓ | ✓ | 仅本人 | ✗ |
| 查看已提交/已通过 | ✓ | ✓ | ✓ | 仅已通过 |
| 创建成果 | ✓ | ✓ | ✓ | ✗ |
| 编辑成果 | ✓ | ✓ | 仅本人草稿 | ✗ |
| 提交审核 | ✓ | ✓ | ✓ | ✗ |
| 审核通过/退回 | ✓ | ✗ | ✗ | ✗ |
| 删除成果 | ✓ | ✓ | 仅本人草稿 | ✗ |

---

## Web界面使用指南

### 登录系统

1. 打开浏览器访问 `http://127.0.0.1:8080`
2. 输入用户名和密码
3. 点击"登录"按钮

### 仪表盘

登录后首先看到仪表盘，展示：

- **成果总数统计**：按类型分类显示
- **待审核提醒**：显示待审核成果数量（仅PI可见）
- **快速操作**：添加成果、查看成员、查看项目的快捷入口

### 成果管理

#### 添加成果

1. 点击"成果管理" → "添加成果"
2. 选择成果类型（论文/专利/软著/会议/项目/数据）
3. 填写基本信息：
   - **成果ID**：自动生成或手动输入
   - **标题**：必填
   - **年份**：必填
   - **负责人**：从成员列表选择
   - **参与人**：可多选
   - **关联项目**：可多选
4. 填写类型专属字段（如论文的期刊、DOI等）
5. 点击"保存"

#### 使用外部数据抓取

系统支持从外部数据源自动填充成果信息：

**方式一：通过DOI抓取**

1. 点击"成果管理" → "从DOI/PubMed抓取"
2. 选择"DOI"标签
3. 输入DOI（如：`10.1038/nature12345`）
4. 点击"抓取"
5. 系统自动填充标题、作者、期刊、年份等信息
6. 检查并补充其他字段后保存

**方式二：通过PubMed ID抓取**

1. 选择"PubMed"标签
2. 输入PMID（如：`12345678`）
3. 点击"抓取"
4. 系统自动填充文献信息

**方式三：上传文档识别**

1. 选择"上传文档"标签
2. 上传PDF、Word或TXT文件
3. 系统尝试识别标题、年份、摘要
4. 人工检查并补充完整信息

#### 编辑成果

1. 在成果列表中找到目标成果
2. 点击"编辑"按钮
3. 修改信息后保存

> **注意**：已提交审核的成果不可编辑，需先退回为草稿状态。

#### 提交审核

1. 确保成果信息完整准确
2. 点击成果详情页的"提交审核"按钮
3. 成果状态变为"待审核"
4. 等待PI审核

#### 审核成果（仅PI）

1. 在"待审核成果"列表中查看
2. 点击成果查看详情
3. 选择操作：
   - **通过**：成果状态变为"已通过"
   - **退回**：成果退回给提交人，需填写退回原因

#### 删除成果

1. 在成果列表中找到目标成果
2. 点击"删除"按钮
3. 确认删除操作

> **权限限制**：
> - 普通成员只能删除自己创建的草稿状态成果
> - PI和管理员可以删除任何成果
> - 系统会检查引用关系，防止误删

### 成员管理

#### 添加成员

1. 点击"成员管理" → "添加成员"
2. 填写信息：
   - **成员ID**：唯一标识符（如工号、姓名拼音）
   - **姓名**：必填
   - **角色**：从PI/管理员/成员/只读中选择
   - **邮箱**：可选
   - **电话**：可选
3. 点击"保存"

#### 编辑成员

1. 在成员列表中找到目标成员
2. 点击"编辑"按钮
3. 修改信息后保存

#### 删除成员

1. 在成员列表中找到目标成员
2. 点击"删除"按钮
3. 确认删除

> **注意**：如果成员已关联成果，系统会阻止删除并提示先解除关联。

### 项目管理

#### 添加项目

1. 点击"项目管理" → "添加项目"
2. 填写信息：
   - **项目ID**：唯一标识符
   - **项目名称**：必填
   - **项目类型**：基金/课题/协作
   - **负责人**：从成员列表选择
   - **开始时间**：可选
   - **结束时间**：可选
3. 点击"保存"

#### 编辑和删除项目

操作方式与成员管理类似。

### 账号管理

#### 修改密码

1. 点击右上角用户名 → "账号管理"
2. 输入当前密码
3. 输入新密码（至少8位，包含字母和数字）
4. 确认新密码
5. 点击"修改密码"

### 统计与导出

#### 查看统计

1. 点击"统计"菜单
2. 查看按类型、年份、状态的成果分布
3. 查看成员贡献排行
4. 查看项目产出统计

#### 导出Excel报告

1. 点击"导出" → "Excel报告"
2. 系统生成包含4个工作表的报告：
   - **汇总统计**：成果类型、年份分布
   - **成果清单**：所有成果详细信息
   - **成员清单**：所有成员信息
   - **项目清单**：所有项目信息
3. 下载文件后用Excel打开

#### 导出CSV

1. 点击"导出" → "CSV文件"
2. 选择导出内容（成果/成员/项目）
3. 下载CSV文件

---

## 命令行工具使用指南

命令行工具适合批量操作和自动化场景。

### 基本语法

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli [选项] <命令> [参数]
```

### 全局选项

- `--data-dir <路径>`：指定数据目录（默认：`data/local/`）
- `--help`：显示帮助信息

### 成员管理命令

**添加成员**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  members add \
  --id alice \
  --name "Alice Zhang" \
  --role member \
  --email "alice@example.com"
```

**列出成员**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli members list
```

**删除成员**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli members remove --id alice
```

### 项目管理命令

**添加项目**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  projects add \
  --id proj-2026-001 \
  --name "国家自然科学基金项目" \
  --type funding \
  --owner alice
```

**列出项目**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli projects list
```

### 成果管理命令

**添加论文成果**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  outputs add \
  --id LW-2026-001 \
  --title "肠道微生物研究" \
  --type article \
  --owner alice \
  --project proj-2026-001 \
  --year 2026 \
  --article-type research \
  --journal "Nature Medicine" \
  --doi 10.1038/nm.2026.001
```

**提交审核**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  outputs submit LW-2026-001 \
  --actor-id alice \
  --actor-role member
```

**审核通过（需PI权限）**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  outputs approve LW-2026-001 \
  --actor-id pi-1 \
  --actor-role pi
```

**审核退回（需PI权限）**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  outputs return LW-2026-001 \
  --actor-id pi-1 \
  --actor-role pi \
  --reason "请补充摘要和关键词"
```

**列出成果**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli outputs list
```

### 统计命令

**查看汇总统计**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli stats summary
```

### 导出命令

**导出CSV**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  export csv \
  --output /tmp/outputs.csv
```

**导出Excel**

```bash
PYTHONPATH=src python3 -m lab_literature_manager.cli \
  export excel \
  --output /tmp/report.xlsx
```

---

## 常见问题

### 1. 忘记管理员密码怎么办？

**解决方法**：

1. 停止Web服务
2. 删除 `data/local/accounts.json` 文件
3. 重新启动服务，系统会重新创建默认管理员账号
4. 使用默认账号登录后修改密码

### 2. 成果无法删除怎么办？

**可能原因**：

- 权限不足（普通成员只能删除自己的草稿）
- 成果已提交审核或已通过

**解决方法**：

- 联系PI或管理员删除
- 或先将成果退回为草稿状态

### 3. DOI抓取失败怎么办？

**可能原因**：

- DOI格式错误
- 网络连接问题
- CrossRef服务暂时不可用
- 未安装 `requests` 库

**解决方法**：

- 检查DOI格式（例如：`10.1038/nature12345`）
- 检查网络连接
- 稍后重试
- 安装依赖：`pip3 install requests`
- 手动填写成果信息

### 4. Excel导出没有格式化？

**原因**：未安装 `openpyxl` 库

**解决方法**：

```bash
pip3 install openpyxl
```

安装后重新导出。

### 5. 如何备份数据？

**方法**：直接备份 `data/local/` 目录

```bash
# 备份
cp -r data/local/ data/backup-$(date +%Y%m%d)/

# 或压缩备份
tar -czf backup-$(date +%Y%m%d).tar.gz data/local/
```

### 6. 如何恢复数据？

**方法**：将备份文件复制回 `data/local/` 目录

```bash
# 从目录恢复
cp -r data/backup-20260701/ data/local/

# 从压缩包恢复
tar -xzf backup-20260701.tar.gz
```

### 7. 如何在其他电脑上使用？

**方法一**：复制整个项目目录

```bash
# 在旧电脑上
tar -czf research-system.tar.gz research-group-file-management/

# 在新电脑上
tar -xzf research-system.tar.gz
cd research-group-file-management
PYTHONPATH=src python3 -m lab_literature_manager.cli web serve
```

**方法二**：只同步数据

1. 复制 `data/local/` 目录到新电脑的相同位置
2. 在新电脑上重新安装系统代码
3. 启动服务

### 8. 多人如何协作使用？

**当前版本**：仅支持单机使用，不支持网络多用户同时访问。

**协作方案**：

- **方案一**：在局域网内部署，局域网用户通过IP访问（需修改服务器监听地址）
- **方案二**：定期导出Excel报告汇总，由一人统一录入
- **方案三**：使用Git同步数据目录（需注意冲突）

---

## 故障排除

### 启动失败

**问题表现**：运行启动命令后报错

**检查步骤**：

1. 确认Python版本：`python3 --version`（需3.9+）
2. 确认在项目根目录：`ls -l src/lab_literature_manager/`
3. 检查端口占用：`lsof -i :8080`（macOS/Linux）或 `netstat -ano | findstr 8080`（Windows）
4. 查看完整错误信息

**常见错误**：

- `ModuleNotFoundError`：未设置 `PYTHONPATH=src`
- `Address already in use`：端口被占用，换一个端口或关闭占用进程

### 数据丢失

**症状**：之前添加的数据看不到了

**可能原因**：

- 使用了不同的 `--data-dir` 参数
- 数据文件被误删或损坏

**解决方法**：

1. 检查数据目录：`ls -l data/local/`
2. 确认启动命令的 `--data-dir` 参数
3. 从备份恢复

### 界面乱码

**症状**：网页显示乱码

**解决方法**：

1. 确认浏览器编码设置为UTF-8
2. 清除浏览器缓存后重新访问
3. 尝试其他浏览器（推荐Chrome、Firefox、Edge）

### 性能问题

**症状**：系统响应慢，加载时间长

**可能原因**：

- 数据量过大（数千条成果）
- 系统资源不足

**优化方法**：

1. 定期归档旧数据
2. 关闭其他占用资源的程序
3. 使用更高配置的电脑

---

## 联系与支持

如有其他问题或建议，请联系：

- **技术支持邮箱**：（待填写）
- **问题反馈**：（待填写）
- **用户手册更新日期**：2026年7月

---

**本手册版本**：V1.0  
**最后更新时间**：2026年7月1日

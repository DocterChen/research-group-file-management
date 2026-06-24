# 权限矩阵

## 角色

- `pi`
- `admin`
- `member`
- `readonly`

## MVP 权限规则

| 权限 | pi | admin | member | readonly |
|------|----|-------|--------|----------|
| `view` | 是 | 是 | 仅自己负责的成果 | 否 |
| `create` | 是 | 是 | 仅自己负责的成果 | 否 |
| `edit` | 是 | 是 | 仅自己负责且状态为 `draft` / `returned` 的成果 | 否 |
| `review` | 是 | 是 | 否 | 否 |
| `export` | 是 | 是 | 否 | 否 |
| `view_audit_log` | 是 | 是 | 否 | 否 |
| `archive` | 是 | 是 | 否 | 否 |
| `delete` | 是 | 是 | 否 | 否 |

## 当前实现说明

- 管理员和 PI 拥有全部管理权限，可查看、审核、导出和维护全部成果。
- 普通成员只可查看、创建、编辑和提交自己作为负责人的成果。
- Web UI 已在仪表盘、成果列表、成果详情和导出端点进行服务端权限过滤。
- CLI 当前已实现 `create`、`review`、`export` 的核心判断。
- 成员新增成果时，默认以第一个 `owner` 作为提交人身份。
- 审核流当前支持：
  - `draft -> submitted`
  - `submitted -> approved`
- `returned`、`archived` 和删除申请流程留待下一阶段扩展。

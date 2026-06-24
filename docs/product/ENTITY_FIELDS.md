# 实体字段说明

## ResearchOutput

通用字段：

- `output_id`：稳定成果 ID
- `title`：成果标题
- `output_type`：成果类型，界面显示为中文；底层枚举保持英文值以兼容既有数据
- `owner_member_ids`：负责人列表，可保存成员 ID，也可保存未建档成员或外部合作者姓名
- `participant_member_ids`：参与人列表，可保存成员 ID，也可保存未建档成员或外部合作者姓名
- `project_ids`：关联项目 ID 列表
- `year`：成果年份
- `keywords`：关键词
- `summary`：摘要或简述
- `notes`：备注
- `review_status`：审核状态
- `created_at`
- `updated_at`

文章专属字段：

- `article_type`
- `journal`
- `doi`
- `issn`
- `pmid`
- `publication_year`
- `volume`
- `issue`
- `pages`
- `impact_factor`
- `jcr_quartile`
- `cas_quartile`
- `submission_status`
- `first_authors`
- `corresponding_authors`

## Member

- `member_id`
- `name`
- `role`
- `email`
- `notes`

## Project

- `project_id`
- `name`
- `project_type`
- `owner_member_ids`：负责人列表，可保存成员 ID，也可保存未建档负责人姓名
- `funding_source`
- `start_year`
- `end_year`

## WorkspaceSettings

- `workspace_name`：首次初始化时设置的工作区名称，例如“马老师课题组”
- `workspace_subtitle`：工作台副标题，默认“成果管理与审核工作台”

## ReviewRecord

- `review_id`
- `output_id`
- `actor_member_id`
- `actor_role`
- `from_status`
- `to_status`
- `comment`
- `created_at`

## AuditLog

- `log_id`
- `entity_type`
- `entity_id`
- `action`
- `actor_member_id`
- `actor_role`
- `summary`
- `created_at`

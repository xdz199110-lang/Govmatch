# 字段映射表（USAspending → 本地数据库）

| 本地字段名           | API字段名（显示标签）      | 数据类型      | 说明                     |
|--------------------|--------------------------|--------------|--------------------------|
| award_id           | Award ID                 | TEXT         | 合同唯一标识              |
| recipient_name     | Recipient Name           | TEXT         | 中标企业名称              |
| award_amount       | Award Amount             | NUMERIC      | 合同金额（美元）          |
| action_date        | Action Date              | DATE         | 发布日期（可能为空）       |
| start_date         | Start Date               | DATE         | 合同开始日期              |
| internal_id        | generated_internal_id    | TEXT         | 内部唯一ID（备用）         |
| naics_code         | naics_code               | VARCHAR(10)  | 行业代码（需额外请求）     |
| set_aside_type     | set_aside_type           | TEXT         | 小企业预留类型（需额外）   |
| description        | description              | TEXT         | 合同简述（需额外）         |

注意：API返回的字段名是带空格的显示标签，我们在代码中会使用这些标签名。
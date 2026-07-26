# 试点前公平性最低协议（PR7）

> 状态：完整基线已落地（监控、代理变量审计、合法分组接口、置信区间、版本与申诉闭环）。  
> 本协议不构成法律意见。

## 1. 产品硬规则

1. 匹配分、可信度、推荐 Top-K **仅为辅助信息**，**禁止**用于自动淘汰候选人。
2. 最终面试邀请与录用决定必须由招聘方人工作出。
3. UI / API 文案不得暗示“系统已证明候选人优劣”或“自动筛选通过”。
4. 为评测公平性 **不得擅自收集** 性别、年龄、民族、健康等敏感个人信息。

管理端接口：

- `GET /analytics/fairness/baseline`
- `POST /analytics/fairness/baseline`（可选提交去标识化合法分组；必须 `legal_basis_attested=true`）

## 2. 监控指标

按 **岗位族（role_family）** 做运营统计（不是人口组）：

| 指标 | 说明 |
|------|------|
| 分数分布 | mean / median / 分桶 + mean 置信区间 |
| Top-K 占比 | 进入岗位推荐 Top-K 的份额 |
| 邀请/录用率 | `interview_invited` / `accepted` + Wilson 区间 |
| impact ratio（岗位族） | **不计算**；职业漏斗基准率不同 |

样本量阈值：每组 `< 30` 标记 `underpowered`，不下确定性结论。

## 3. 代理变量审计

对业务代理变量做分数分布抽查（可能误分类，仅供人工复核）：

- 学校层级（从简历教育字段关键词推断：985/211/双一流/其他）
- 地区（简历/岗位 location）
- 语言风格（摘要 latin/cjk 占比）

输出见 `proxy_variable_audit`，各组含 mean CI 与 underpowered 标记。

## 4. 合法去标识化分组 impact ratio

仅当运营方完成合规评审并在请求中显式 `legal_basis_attested=true` 时，才对提交的
`{group_id, applicants, selected}` 计算 selection rate / impact ratio（含 Wilson CI）。

未证明合法基础时返回 `legal_group_impact_ratio.status=blocked`。

## 5. 标签与偏差

以下信号 **只能作为带偏差风险的观察值**：

- 招聘方 `useful` 反馈
- 面试邀请
- 历史录用结果

## 6. 版本、申诉与披露

响应字段：

- `model_versions`：matching_rules / credibility_rules / rerank_model
- `human_review_and_appeals`：澄清线程、人工状态变更、面试同意、隐私更正删除
- `pilot_disclosure`：必须披露样本量、置信区间、限制；样本不足不下结论

## 7. 回滚

关闭 fairness 端点不影响主业务。Worker / 匹配链路不依赖该监控出口。

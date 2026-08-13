# C5 Hypothesis Evaluation / C5 假设评测

## 中文

QLink 将信息不足时的推断保存为独立的“待验证假设”，而不是简历事实、Claim 或招聘结论。每个待确认问题最多生成两条假设，并保存来源、规则版本和验证状态。

验证状态只有四种：`hypothesis`、`user_confirmed`、`evidence_supported`、`rejected`。本人确认只更新假设状态；不会自动创建 Claim 或改写简历。`evidence_supported` 还必须引用候选人本人拥有、未撤回的 Evidence Artifact。

离线复现：

```bash
make evaluate-hypotheses
```

仓库内的 `hypothesis_eval_synthetic_v1.json` 只有 3 个合成案例。加载器会拒绝身份字段、错误池标签和非 `synthetic-` 样本 ID。真实确认样本的仓库清单保持为空；未来只能进入另一个私有、经同意的存储，不得混入合成 CI 集。

当前结果：3/3 合成案例通过，真实确认样本使用数为 0。这个结果只验证边界和确定性行为，不证明假设对真实用户有帮助。该效果必须在 C6 经用户同意的试点中评估。

## English

When information is incomplete, QLink persists a separate validation hypothesis—not a resume fact, Claim, or hiring conclusion. Each unresolved issue receives at most two hypotheses with source references, a rule version, and an explicit validation state.

Run the offline check with `make evaluate-hypotheses`. The checked-in dataset contains three synthetic cases. Its loader rejects identity fields, pool mismatches, and sample IDs without the `synthetic-` prefix. The real-confirmed manifest is intentionally empty; future consented samples must remain in a separate private store.

Current result: 3/3 synthetic boundary cases pass and zero real-confirmed samples are used. This demonstrates deterministic safety boundaries, not real-world usefulness; that question belongs to the consented C6 pilot.

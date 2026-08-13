# QLink contribution conventions

## Contribution licensing

QLink's core platform is licensed under `AGPL-3.0-only`, and the copyright holder may also offer separate commercial licenses. Focused bug reports, product feedback, and reproducible issues are welcome.

Until the project publishes a contributor agreement that explicitly supports this dual-licensing model, maintainers should not merge third-party code contributions. A `Signed-off-by` line or Developer Certificate of Origin alone must not be treated as permission to relicense a contributor's copyright.

Before preparing a pull request, open an issue to confirm whether the contributor agreement is available and whether the proposed scope can be accepted.

QLink 核心平台采用 `AGPL-3.0-only`，版权所有人也可能提供独立商业授权。欢迎提交范围清晰、可以复现的 Issue 和产品反馈。

在项目发布明确支持双重授权的贡献者协议之前，维护者不应合并第三方代码贡献。仅有 `Signed-off-by` 或 Developer Certificate of Origin 不应被视为允许重新授权贡献者版权。

## Branch names

Use a short, descriptive branch with one product or technical area:

```text
<type>/<area>-<short-purpose>
```

Allowed `type` values:

- `feat` — user-visible capability;
- `fix` — defect correction;
- `sec` — authorization, privacy or security correction;
- `refactor` — behavior-preserving architecture cleanup;
- `perf` — measured performance work;
- `test` — test-only work;
- `docs` — documentation-only work;
- `chore` — tooling or repository maintenance;
- `release` — release preparation.

Examples:

```text
feat/matching-domain-lanes
feat/interview-practice-brief
fix/advisor-private-job-history
sec/target-job-ownership
refactor/matching-signal-boundaries
perf/diagnostic-query-indexes
```

Do not put unrelated product areas in one branch. A defect should be locatable from the branch name without opening its diff.

Existing shared or default branches are migration exceptions. Rename them only after the worktree is clean, open pull requests and CI references have been checked, and collaborators have been notified.

## Commit subjects

Use Conventional Commit-style subjects:

```text
feat(matching): keep exploration inside the candidate role family
fix(advisor): restore private imported jobs for their owner
sec(diagnostics): reject cross-candidate private job access
refactor(signals): remove brand prestige and fake outcome probabilities
```

## Change boundaries

Every product change should identify:

1. the user task it advances;
2. the existing object or endpoint it reuses;
3. the product invariant it must preserve;
4. the test or measurement that proves the change works.

AI inference is never persisted as a user fact without a separate confirmation or evidence state.

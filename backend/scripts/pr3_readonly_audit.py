#!/usr/bin/env python3
"""PR3 read-only application data audit.

The script refuses likely production targets, prints only a sanitized target,
uses a read-only transaction with a statement timeout, and never outputs PII
or resume content.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env", override=False)

SAFE_SOURCES = {"candidate_applied", "candidate_consented"}


def _environment(host: str, database: str) -> str:
    host_lower = (host or "").lower()
    database_lower = (database or "").lower()
    if "test" in database_lower:
        return "test"
    if any(marker in database_lower for marker in ("prod", "production")):
        return "possible_production"
    if host_lower not in {"localhost", "127.0.0.1", "::1"}:
        return "possible_production"
    return "development"


def _masked_id(value: Any) -> str:
    if value is None:
        return "none"
    digest = hashlib.sha256(f"pr3-audit:{value}".encode()).hexdigest()
    return f"id:{digest[:12]}"


def _finding(
    *,
    category: str,
    ids: list[str],
    risk: str,
    recommendation: str,
    auto_migrate: bool,
    manual_confirmation: bool,
) -> dict[str, Any]:
    return {
        "category": category,
        "count": len(ids),
        "masked_ids": sorted({_masked_id(item) for item in ids})[:20],
        "risk": risk,
        "recommendation": recommendation,
        "auto_migrate": auto_migrate,
        "manual_confirmation": manual_confirmation,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    target = report["target"]
    lines = [
        "# PR3 真实数据只读审计报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 目标：`{target['host']}:{target['port']}/{target['database']}`",
        f"- 环境判断：`{target['environment']}`",
        f"- 事务：`{report['transaction']}`",
        f"- 状态：`{report['status']}`",
    ]
    if report.get("blocker"):
        lines.extend(["", "## 环境阻断", "", report["blocker"]])
        return "\n".join(lines) + "\n"

    lines.extend(["", "## Application 状态数量", ""])
    for status, count in report["status_counts"].items():
        lines.append(f"- `{status}`：{count}")

    lines.extend(["", "## 风险分类", ""])
    for finding in report["findings"]:
        lines.extend(
            [
                f"### {finding['category']}",
                f"- 数量：{finding['count']}",
                f"- 风险：{finding['risk']}",
                f"- 脱敏 ID：{', '.join(finding['masked_ids']) or '无'}",
                f"- 推荐处理：{finding['recommendation']}",
                f"- 可自动迁移：{'是' if finding['auto_migrate'] else '否'}",
                f"- 需要人工确认：{'是' if finding['manual_confirmation'] else '否'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


async def _audit(database_url: str, timeout_ms: int) -> dict[str, Any]:
    parsed = make_url(database_url)
    host = parsed.host or ""
    port = parsed.port or (5432 if parsed.get_backend_name() == "postgresql" else 0)
    database = parsed.database or ""
    environment = _environment(host, database)
    target = {
        "host": host,
        "port": port,
        "database": database,
        "environment": environment,
    }
    print(
        f"PR3 audit target: host={host} port={port} database={database} environment={environment}"
    )
    if environment == "possible_production":
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target": target,
            "transaction": "not_started",
            "status": "blocked",
            "blocker": ("目标可能是生产环境；未建立连接。必须由用户确认目标后另行执行。"),
        }

    engine = create_async_engine(database_url, echo=False, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await conn.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{timeout_ms}ms"},
                )
                schema_rows = (
                    (
                        await conn.execute(
                            text(
                                "SELECT table_name, column_name "
                                "FROM information_schema.columns "
                                "WHERE table_schema = 'public' "
                                "AND table_name IN "
                                "('job_applications', 'credibility_audit_records', "
                                "'interview_invitations')"
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                schema: defaultdict[str, set[str]] = defaultdict(set)
                for row in schema_rows:
                    schema[row["table_name"]].add(row["column_name"])

                if "job_applications" in schema:
                    pipeline_expr = (
                        "pipeline_meta"
                        if "pipeline_meta" in schema["job_applications"]
                        else "NULL::jsonb AS pipeline_meta"
                    )
                    applications = (
                        (
                            await conn.execute(
                                text(
                                    "SELECT id, status, resume_id, job_id, candidate_id, "
                                    f"employer_id, {pipeline_expr} FROM job_applications"
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                else:
                    applications = []

                if "credibility_audit_records" in schema:
                    application_expr = (
                        "application_id"
                        if "application_id" in schema["credibility_audit_records"]
                        else "NULL::varchar AS application_id"
                    )
                    report_expr = (
                        "report"
                        if "report" in schema["credibility_audit_records"]
                        else "NULL::jsonb AS report"
                    )
                    audits = (
                        (
                            await conn.execute(
                                text(
                                    f"SELECT id, {application_expr}, {report_expr} "
                                    "FROM credibility_audit_records"
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                else:
                    audits = []

                if "interview_invitations" in schema:
                    application_expr = (
                        "application_id"
                        if "application_id" in schema["interview_invitations"]
                        else "NULL::varchar AS application_id"
                    )
                    invitations = (
                        (
                            await conn.execute(
                                text(
                                    f"SELECT id, {application_expr}, job_id, candidate_id, "
                                    "employer_id, resume_id, status "
                                    "FROM interview_invitations"
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                else:
                    invitations = []
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

    status_counts = Counter(row["status"] or "unknown" for row in applications)
    closed_but_clarified: list[str] = []
    resume_mismatch: list[str] = []
    missing_initial: list[str] = []
    missing_current: list[str] = []
    invalid_versions: list[str] = []
    terminal_reversal: list[str] = []
    ambiguous_source: list[str] = []

    application_by_id = {str(row["id"]): row for row in applications}
    duplicate_app_groups: defaultdict[tuple[str, str], list[str]] = defaultdict(list)

    for row in applications:
        app_id = str(row["id"])
        meta = row["pipeline_meta"] if isinstance(row["pipeline_meta"], dict) else {}
        threads = (meta.get("claim_threads") or {}).values()
        if row["status"] == "clarified" and any(
            thread.get("closed_by_employer") or thread.get("status") == "closed"
            for thread in threads
            if isinstance(thread, dict)
        ):
            closed_but_clarified.append(app_id)

        initial = meta.get("initial_submission_snapshot")
        if not isinstance(initial, dict):
            missing_initial.append(app_id)

        current_version_id = meta.get("current_resume_version_id")
        if not current_version_id:
            missing_current.append(app_id)

        versions = meta.get("resume_versions")
        version_ids: list[str] = []
        current_version = None
        if isinstance(versions, list):
            for version in versions:
                if not isinstance(version, dict):
                    continue
                version_id = version.get("version_id")
                if version_id:
                    version_ids.append(str(version_id))
                if version_id == current_version_id:
                    current_version = version
        if (
            not versions
            or len(version_ids) != len(set(version_ids))
            or (current_version_id and current_version is None)
        ):
            invalid_versions.append(app_id)

        snapshot_resume_id = (
            current_version.get("resume_id") if isinstance(current_version, dict) else None
        )
        if snapshot_resume_id and str(snapshot_resume_id) != str(row["resume_id"]):
            resume_mismatch.append(app_id)

        terminal_seen = False
        for event in meta.get("status_history") or []:
            if not isinstance(event, dict):
                continue
            source, target_status = event.get("from"), event.get("to")
            if (terminal_seen and target_status not in {"accepted", "rejected"}) or (
                source in {"accepted", "rejected"} and target_status != source
            ):
                terminal_reversal.append(app_id)
                break
            terminal_seen = terminal_seen or target_status in {"accepted", "rejected"}

        source = meta.get("application_source")
        if (
            source not in SAFE_SOURCES
            or meta.get("migration_uncertain") is True
            or meta.get("snapshot_status") in {"legacy_missing", "legacy_unverified"}
        ):
            ambiguous_source.append(app_id)

        duplicate_app_groups[(str(row["job_id"]), str(row["candidate_id"]))].append(app_id)

    audit_missing_binding: list[str] = []
    for audit in audits:
        report = audit["report"] if isinstance(audit["report"], dict) else {}
        snapshot = report.get("application_resume_snapshot")
        if not isinstance(snapshot, dict) or not all(
            snapshot.get(field) for field in ("version_id", "resume_id", "content_hash")
        ):
            audit_missing_binding.append(str(audit["id"]))

    invitation_mismatch: list[str] = []
    pending_groups: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)
    for invitation in invitations:
        invitation_id = str(invitation["id"])
        app = application_by_id.get(str(invitation["application_id"]))
        if app is None or any(
            str(invitation[field]) != str(app[field])
            for field in ("job_id", "candidate_id", "employer_id", "resume_id")
        ):
            invitation_mismatch.append(invitation_id)
        if invitation["status"] == "pending":
            pending_groups[
                (
                    str(invitation["application_id"]),
                    str(invitation["job_id"]),
                    str(invitation["candidate_id"]),
                )
            ].append(invitation_id)

    duplicate_pending_ids = [
        invitation_id for ids in pending_groups.values() if len(ids) > 1 for invitation_id in ids
    ]
    duplicate_application_ids = [
        app_id for ids in duplicate_app_groups.values() if len(ids) > 1 for app_id in ids
    ]

    findings = [
        _finding(
            category="PR3 审计所需表或字段缺失",
            ids=[
                f"schema:{name}"
                for name, required in {
                    "job_applications.pipeline_meta": (
                        "pipeline_meta" in schema.get("job_applications", set())
                    ),
                    "credibility_audit_records": ("credibility_audit_records" in schema),
                    "interview_invitations.application_id": (
                        "application_id" in schema.get("interview_invitations", set())
                    ),
                }.items()
                if not required
            ],
            risk="high",
            recommendation="保持只读；先设计正式、可回滚的 PR7 schema 迁移",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="employer closed Claim 但 application 为 clarified",
            ids=closed_but_clarified,
            risk="high",
            recommendation="人工确认关闭语义后再执行状态迁移",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="application resume 与当前 version/snapshot 不一致",
            ids=resume_mismatch,
            risk="high",
            recommendation="核对历史版本来源，禁止用当前 Resume 冒充历史快照",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="缺少 initial_submission_snapshot",
            ids=missing_initial,
            risk="high",
            recommendation="仅从可证明的历史来源回填，否则标记 legacy_missing",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="缺少 current_resume_version_id",
            ids=missing_current,
            risk="medium",
            recommendation="核对 resume_versions 后建立指针",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="resume_versions 为空、指针无效或版本号重复",
            ids=invalid_versions,
            risk="high",
            recommendation="人工确认版本顺序后使用幂等迁移",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="AuditRecord 缺少 snapshot/version 绑定",
            ids=audit_missing_binding,
            risk="high",
            recommendation="历史审计不可自动绑定当前简历；保留为 legacy audit",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="终态后发生状态回退",
            ids=terminal_reversal,
            risk="critical",
            recommendation="逐条审查 history，不自动改写",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="Invitation 与 application/job/candidate/resume 不一致",
            ids=invitation_mismatch,
            risk="critical",
            recommendation="冻结相关邀请并人工核对租户及版本归属",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="多个 pending invitation 重复组",
            ids=duplicate_pending_ids,
            risk="high",
            recommendation="人工选择保留记录后再增加正式唯一约束",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="相同 job+candidate 多个 application",
            ids=duplicate_application_ids,
            risk="high",
            recommendation="人工确认主记录及关联消息后再合并",
            auto_migrate=False,
            manual_confirmation=True,
        ),
        _finding(
            category="来源不明或迁移存在歧义",
            ids=ambiguous_source,
            risk="high",
            recommendation="保持默认不授权，进入人工迁移清单",
            auto_migrate=False,
            manual_confirmation=True,
        ),
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "transaction": f"read_only; statement_timeout={timeout_ms}ms; rolled_back",
        "status": "completed",
        "status_counts": dict(sorted(status_counts.items())),
        "findings": findings,
    }


async def _main(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured")

    try:
        report = await _audit(database_url, args.statement_timeout_ms)
    except Exception as exc:
        parsed = make_url(database_url)
        host = parsed.host or ""
        port = parsed.port or 5432
        database = parsed.database or ""
        environment = _environment(host, database)
        print(
            f"PR3 audit connection failed: host={host} port={port} "
            f"database={database} environment={environment}"
        )
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target": {
                "host": host,
                "port": port,
                "database": database,
                "environment": environment,
            },
            "transaction": "not_started_or_rolled_back",
            "status": "blocked",
            "blocker": f"配置数据库不可连接：{type(exc).__name__}",
        }

    output = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else _render_markdown(report)
    )
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output, encoding="utf-8")
        print(f"PR3 audit report saved: {output_path}")
    else:
        print(output, end="")
    return 0 if report["status"] == "completed" else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="PR3 read-only data audit")
    parser.add_argument("--database-url", help="Optional URL; defaults to DATABASE_URL")
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=10_000,
        help="Per-statement timeout in milliseconds",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", help="Report output path")
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()

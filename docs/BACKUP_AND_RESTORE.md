# Backup and Restore / 备份与恢复

QLink's default Docker deployment stores private data in PostgreSQL plus two file volumes: ordinary uploads and the Evidence Vault. A backup is incomplete unless all three are recoverable.

QLink 默认 Docker 部署把私有数据保存在 PostgreSQL 和两个文件卷中：普通上传文件及 Evidence Vault。只有三者都可恢复时，备份才是完整的。

## Create a backup / 创建备份

Run against the intended Compose project and environment file:

```bash
COMPOSE_ENV_FILE=/secure/path/production.env \
COMPOSE_PROJECT_NAME=qlink-production \
BACKUP_DIR=/secure/off-host/location \
make backup
```

The timestamped directory contains `database.dump`, `uploads.tar.gz`, `evidence-vault.tar.gz`, `FORMAT_VERSION`, `STATUS`, and `SHA256SUMS`. The script uses a private process umask. Copy completed backups to encrypted off-host storage with access logging and a retention policy; do not commit them to Git.

时间戳目录包含数据库、普通上传、证据库、格式版本、完成状态及校验和。脚本使用私有文件权限掩码。请把完整备份复制到具有访问日志和保留策略的异地加密存储，禁止提交到 Git。

## Restore rehearsal / 恢复演练

Restoration overwrites the selected environment. Resolve and verify the project name and backup path first, then use only a disposable synthetic environment:

```bash
CONFIRM_RESTORE=RESTORE_AND_OVERWRITE \
COMPOSE_ENV_FILE=/secure/path/rehearsal.env \
COMPOSE_PROJECT_NAME=qlink-restore-rehearsal \
./scripts/restore.sh /secure/off-host/location/20260815T120000Z
```

The restore verifies checksums before stopping services, restores all three data stores, reruns migrations, recreates the proxy, and checks public readiness. Afterwards, manually verify one synthetic database record, uploaded file, and Evidence Vault artifact.

恢复过程会在停止服务前验证校验和，恢复三类数据，重新执行迁移、重建代理并检查公开 readiness。完成后还应人工验证一条合成数据库记录、一个普通上传文件和一个 Evidence Vault 文件。

Backups created before format version 2 do not contain Evidence Vault files and are rejected by default. The emergency override printed by the script acknowledges known data loss; it does not make a legacy backup complete.

格式版本 2 以前的备份不包含 Evidence Vault，默认会被拒绝。脚本提示的紧急覆盖参数只表示接受已知的数据缺失，并不能让旧备份变完整。

If `OBJECT_STORAGE_BACKEND=s3`, protect the bucket independently with encryption, versioning or provider backups, least-privilege credentials, and a tested restore procedure. The local Evidence Vault archive does not replace an object-storage backup.

如果使用 `OBJECT_STORAGE_BACKEND=s3`，还必须独立配置桶加密、版本控制或云备份、最小权限凭据和经过演练的恢复流程；本地 Evidence Vault 压缩包不能替代对象存储备份。

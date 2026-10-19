# 部署與維護

## 已驗證與未驗證
本次驗證：Python 3.12、Django 5.2、SQLite 檔案資料庫、Chromium、開發服務、交易／權限測試、實際備份還原。Docker 非root映像與 Gunicorn 功能／重啟持久化已驗證；Caddy 真實 HTTPS 與 PostgreSQL 仍未端到端執行，不可視為已公開部署或已驗證 PostgreSQL。沒有公開發布網站。

## 單機持久化部署（仍為 sandbox）
1. 準備擁有的網域、DNS、80/443、Docker Compose。確認法律／隱私及資料責任主體。
2. 複製 `.env.example` 為 `.env`。以 `python -c 'import secrets; print(secrets.token_urlsafe(64))'` 分別產生 SECRET_KEY 與 WEBHOOK_SECRET，僅在安全終端設定。不得使用範本字串；SECRET_KEY 也用於 MFA seed 加密，必須安全備份。
3. 設定 PUBLIC_HOST、ALLOWED_HOSTS 和 CSRF_TRUSTED_ORIGINS 為同一實際 HTTPS 主機。保留 PAYMENT_MODE=sandbox、REQUIRE_STAFF_MFA=1、DEBUG=0。
4. 在獲授權的部署環境執行 `docker compose up --build -d`。Caddy 自動申請憑證並服務靜態檔案，web 不直接公開。只有受信任反向代理可寫入 X-Forwarded-Proto。
5. `docker compose exec web python manage.py bootstrap_admin ADMIN_NAME --email YOUR_EMAIL`。登入後到 `/account/security/` 啟用 TOTP，再進管理工作臺。另建立審核帳號，由管理員授權。初次角色 bootstrap 可在安全 Django shell 以 `User.objects.create_user` 及 `Group` 建立，密碼用 getpass 讀取，勿寫死命令。
6. `docker compose exec web python manage.py check --deploy --fail-level WARNING`；驗證 HTTPS、語言、真實空資料、求助、MFA、權限與備份。
7. 使用 `jobs` 服務每分鐘重試到期釋放／通知 outbox／保留期清理。失敗應告警，不能將 process healthcheck 取代功能檢查。

持久卷 `data` 保存 SQLite、私人附件及本機金鑰。`static` 是可重建資產。升級後以 `docker compose down` 停 web/jobs（不可 `-v`），在備份後移除並重建僅 `static` 卷以刷新靜態資產，保留所有 data 卷；或使用部署版本獨立 static 卷。

SQLite 使用 IMMEDIATE 交易、30 秒鎖等待、資料庫條件更新及約束，已驗證雙連線搶最後一件。適合單機試營運；不要將同一 SQLite 卷跨主機共享。資料量及吞吐成長時遷移 PostgreSQL，先在 staging 以 PostgreSQL 重跑全部交易、並發、還原及 E2E；目前未聲稱該步已完成。

## 雲端 build container 無 DNS 時

`DOCKER_CONFIG=/tmp/keran-docker-config sh scripts/build-offline-image.sh` 已在本環境建置成功：透過主機正常 TLS 驗證的 pip 下載官方 wheels，再以 BuildKit named context 供容器離線安裝。這不關閉安全驗證，也不把環境金鑰打包進映像。一般可連線部署可用原 Dockerfile。

## PostgreSQL 可選設定
設定 POSTGRES_DB、POSTGRES_USER、POSTGRES_PASSWORD、POSTGRES_HOST、POSTGRES_PORT。使用可信任私網與 TLS 配置，建立獨立最小權限使用者。`migrate` 建表；既有 SQLite 資料以維護窗口導出並在 staging 還原核對，勿直接改環境變數後假定資料已遷移。此路徑需另行部署驗證。

## 備份與還原
SQLite 線上備份：

```sh
DATA_DIR=/path/to/live .venv/bin/python scripts/backup.py /secure-backups/keran.sqlite3
# 僅向新的空目錄還原；工具拒絕覆寫既有 DB。
DATA_DIR=/path/to/restored .venv/bin/python scripts/backup.py /secure-backups/keran.sqlite3 --restore
```

同時加密備份 `DATA_DIR/private`、SECRET_KEY（或本機 `.secret-key`）、環境及應用版本；備份不公開。複製私人檔案前暫停上傳／清理工作以維持一致快照。設定備份保留與存取責任；定期在獨立環境還原，核對 `PRAGMA integrity_check`、`foreign_key_check`、案件／需求、訂單／明細、庫存及財務流水。`scripts/verify_restore.py` 已實際執行資料庫備份／還原及所有業務資料表逐列比對。它不代替私人檔案和密鑰的完整災難復原演練。

PostgreSQL：使用供應商的加密快照與 `pg_dump --format=custom`，於新資料庫 `pg_restore`；驗證外鍵、資料筆數、金額及餘額。將 database 密碼交給 pgpass 或 secret manager，避免命令行或日誌暴露。

## 故障處理
- 庫存預留逾期：執行 `run_jobs`；可安全重跑，檢查 stock movements 與 aid ledger，勿直接 UPDATE 餘額。
- 待付款超時後收到成功：記為 manual_review，不直接出庫。財務須對帳退款或在新核准流程重新配置；現階段 sandbox 訂單的此狀態需維護人員處理，不能自動承諾履約。
- 通知失敗：Outbox 為可靠記錄，重試不改付款成功事實。現僅 sandbox_recorded，沒有真實寄信。
- 退款失敗：不得手動把捐款實收減去，等支付確認；重試需新的退款參照。
- MFA 裝置遺失：需身分核實及另一管理員的維護程序；沒有公開繞過入口。安全 shell 重設前先作外部工單和 Audit 記錄，重新註冊種子。尚無自行下載的 recovery codes。
- 付款事件：僅支援本系統 sandbox 事件適配器，不是 Stripe webhook 協定。不要把 Stripe 原始事件直接送入本 endpoint，也不要把 PAYMENT_MODE 改成 live。

## 第三方接入
實際 hosted checkout、供應商官方 Webhook 驗簽、稅務服務、支付分帳／商家收款能力、電郵／SMS adapter 和真實憑證仍須接入及供應商 sandbox 驗證。現有 domain services、獨立 purpose、idempotency、outbox 和事件帳是接入邊界；不能把模擬器當成正式供應商整合。

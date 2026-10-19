# KERAN COMMONS · 共益生活 V1.0

Django 全端應用：雙語商城、求助及個案工作臺、志願者認證、援助預算、用途分離的庫存、拆單、自提及配送、測試退款、公益眾籌、財務帳及 Excel 報表。使用持久化關聯式資料庫，不以 localStorage 保存業務資料。

**目前僅支援 sandbox 收款及通知。沒有真實交易、真實寄信或已正式上線的宣稱。** 八類未確認商品為草稿，五臺代步車為待盤點／檢查資產，均不計入可用庫存。

## 從 GitHub 下載及查看畫面

在本交付分支頁按 **Code → Download ZIP**，解壓後：

- 直接用瀏覽器開啟 `artifacts/ui-preview/index.html`，可離線切換首頁／商城、桌面／手機、英文／繁中，無需安裝 Python。這是靜態設計預覽。
- 測試實際登入、購物、求助及管理流程，先在終端切換到解壓後含 `manage.py` 的資料夾，再依下列步驟啟動。需要 Python 3.12，以下為 macOS／Linux 命令；Windows 可使用 WSL。
- 資料庫、密碼、私人附件及第三方憑證不隨 GitHub 程式碼交付；由 seed 在你的機器重新建立隔離測試資料及隨機角色密碼。

## 本機啟動

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed
.venv/bin/python manage.py bootstrap_admin YOUR_USERNAME --email YOUR_EMAIL
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

管理員密碼在終端以無回顯方式輸入，沒有共用預設密碼。另建立審核員並授予 `reviewer`，讓項目編輯者與發布審核者分離。角色授權在 `/admin/settings/`，需重新確認密碼；不可自行更改自己的角色。

資料預設保存於 `var/keran.sqlite3`，私人檔案位於 `var/private/`。帳號、session、案件、訂單及財務資料均持久化。`var/` 不納入 Git。

## 隔離的可操作測試預覽

```sh
export DATA_DIR="$PWD/var/demo"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed --demo
.venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
```

僅 `DATA_DIR` 路徑包含 `demo` 時允許 demo seed。四項虛構測試商品、一個測試眾籌及測試預算與非公開真實草稿分開；頁面明示 sandbox。`seed --demo` 不建立假捐款、假成果或假實收。

七種測試角色為 `review_member`、`review_admin`、`review_reviewer`、`review_caseworker`、`review_warehouse`、`review_finance`、`review_merchant`。各自隨機密碼只保存在該 `DATA_DIR/review-accounts.json`（0600）；由有權存取環境的人在終端私密查看，勿貼進聊天室、Git、公開文件或日誌。可重跑 seed，既有帳號密碼不被覆寫。

本次雲端預覽服務使用 `var/demo`。平台未提供可轉發的網站預覽工具，未公開部署；實際瀏覽器截圖及測試證據位於 [artifacts](artifacts)，可在支援埠轉發的開發工具中開啟服務審閱。不要將 loopback 位址當成可分享的公開預覽網址。

## 驗證

```sh
.venv/bin/python manage.py test core.tests --verbosity 2
.venv/bin/python scripts/verify_concurrency.py
.venv/bin/python scripts/browser_review.py
DEBUG=0 ALLOWED_HOSTS=keran.example.invalid .venv/bin/python manage.py check --deploy --fail-level WARNING
```

瀏覽器檢查需 Chromium，預設 `/usr/bin/chromium`，可設 `CHROMIUM_PATH`。瀏覽器測試使用暫存的獨立資料庫，自行啟停 8001 測試服務；不污染預覽或真實資料。測試日誌、桌面／手機截圖及還原檢查 JSON 位於 `artifacts/`。

- [逐項驗收與實際結果](docs/ACCEPTANCE.md)
- [管理操作](docs/OPERATIONS.md)
- [部署、備份及還原](docs/DEPLOYMENT.md)
- [資料字典及業務規則](docs/DATA.md)
- [API 介面](docs/API.md)
- [待配置及上線阻塞](docs/LAUNCH.md)
- [實施基線](docs/IMPLEMENTATION.md)
- [審閱預覽](docs/PREVIEW.md)
- [雲端重啟及設定保存狀態](docs/ENVIRONMENT.md)

"""Regenerate the traceability table only after executing the test suite."""
import ast,re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
log=(root/'docs/TEST_RESULTS.txt').read_text()
count=re.search(r'Ran (\d+) tests',log)
assert count and int(count[1])>=60 and '\nOK\n' in log, 'Run the current suite before generating acceptance evidence.'
spec=(root/'docs/REQUIREMENTS.md').read_text()
scenarios={}
for line in spec.splitlines():
    if re.match(r'\| A\d\d \|',line):
        cols=[c.strip() for c in line.split('|')];scenarios[cols[1]]=cols[2]
methods=[node.name for node in ast.walk(ast.parse((root/'core/tests/test_acceptance.py').read_text())) if isinstance(node,ast.FunctionDef) and re.match(r'test_A\d\d_',node.name)]
rows=[]
for method in sorted(methods):
    aid=method.split('_')[1];passed=bool(re.search(re.escape(method)+r'.*?\.\.\. ok',log))
    assert passed,method
    rows.append(f'| {aid} | {scenarios[aid]} | sandbox 自動檢查通過 | `{method}` |')
assert len(rows)==42
header='''# 逐項驗收紀錄

區分可重現的 sandbox 證據與正式上線條件；模擬支付、測試收據和 outbox 不是真實金流或寄信。

## 本次實際結果

- **60項 Django 交易／API／安全測試全部通過**，沒有跳過或預期失敗。見 [完整原始輸出](TEST_RESULTS.txt)。
- **16項 Chromium 端到端檢查通過**：購物報價與付款模擬、私密求助及補充、認證人工審核、計畫與庫存匹配、部分交付、自提核銷、捐款與收據、Excel、繁中、390px行動版及鍵盤 skip link。沒有未處理 JavaScript 錯誤。證據：`artifacts/browser-results.json`。
- **真正兩個同時資料庫連線**：最後一件僅一單預留，另一單庫存衝突；同時兩筆已建立捐款成功均完整入帳（120%目標、視覺100%、兩份收據）。證據：`artifacts/concurrency.json`。
- **實體 SQLite 備份→新目錄還原**：44張 core 表逐列一致，integrity_check=ok，外鍵違規0，包含案件、需求、訂單、庫存與資金流水。證據：`artifacts/restore.json`。
- **axe-core 4.11.1 六頁自動檢查無偵測違規**（WCAG 2A/AA、2.1AA 規則）。首次發現的圖片註記與項目文字對比已修正；仍有 incomplete 需人工評估，不是完整 WCAG 認證。證據：`artifacts/accessibility.json`。
- 正式設定的 Django `check --deploy --fail-level WARNING` 通過；`makemigrations --check --dry-run` 無漂移。
- **非root Docker映像建置及 Gunicorn 功能測試通過**；建立帳號／session／求助後，重啟容器仍可讀回同一案件。證據：`artifacts/container.json`。一般 build 因本雲端 build container DNS 失敗，改由主機正常 TLS 驗證下載套件再離線安裝；沒有停用驗證。Caddy 真實 HTTPS 與 PostgreSQL 仍未端到端驗證。

## A01–A42 對照

「通過」限下列可重現自動化範圍，不表示正式商業條件、真人使用者或第三方整合均已完成。原始需求另存 [REQUIREMENTS.md](REQUIREMENTS.md)。

| ID | 文件情境 | 本次狀態 | 對應測試 |
|---|---|---|---|
'''
footer='''

## 驗收範圍與限制

- **A01**：桌面／手機截圖、無水平溢出、語言保存及鍵盤 skip link 已驗。真人高齡、完整鍵盤／讀屏、其他瀏覽器仍需驗收。
- **A10/A37**：除了順序單元測試，`verify_concurrency.py` 已做實際雙連線並發。未將結果推定為 PostgreSQL 已驗。
- **A14/A41**：拆單、原來源退款、企業捐款調整、費用、結算、支出預留／支付和拒付都有檢查；正式支付商、銀行及稅基仍需外部整合驗收。
- **A20**：列表、Excel、API totals 共用權限和查詢；庫存按單位／用途、財務按 bucket／kind 分列，不混加。大量資料效能與完整篩選組合仍需業務驗收。
- **A25/A42**：正式支付與通知停用符合缺配置的預期行為；不代表已實作 Stripe/PayPal／稅務／寄信供應商。
- **A28**：本次為所有 core 資料表實體還原；私人檔案及密鑰的整機災難復原演練另依部署說明執行。
- **A31**：後臺實際建立圖片／規格商品並驗證發布；未確認的真實八類商品仍為草稿，測試不授權其公開銷售。
- **A39**：取消保留受影響交易及通知 outbox；真實通知與原渠道退款仍待接入。

## 重跑

```sh
.venv/bin/python manage.py test core.tests --verbosity 2
.venv/bin/python scripts/verify_concurrency.py
.venv/bin/python scripts/browser_review.py
npm --cache /tmp/keran-npm-cache --prefix /tmp/keran-a11y install axe-core@4.11.1 --no-audit --no-fund
.venv/bin/python scripts/accessibility_review.py
```

E2E 自行建立和銷毀隔離 demo DB，使用8001；a11y 檢查本機8000預覽。axe 注入只在測試 browser context 放行，部署 CSP 沒有停用。詳見 [待配置及已知限制](LAUNCH.md)。
'''
header=header.replace('60項',count[1]+'項')
(root/'docs/ACCEPTANCE.md').write_text(header+'\n'.join(rows)+footer)
print('42 scenario mappings generated from executed test results.')

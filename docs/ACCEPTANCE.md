# 逐項驗收紀錄

區分可重現的 sandbox 證據與正式上線條件；模擬支付、測試收據和 outbox 不是真實金流或寄信。

## 本次實際結果

- **63項 Django 交易／API／安全測試全部通過**，沒有跳過或預期失敗。見 [完整原始輸出](TEST_RESULTS.txt)。
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
| A01 | 手機／桌面、英文／中文 | sandbox 自動檢查通過 | `test_A01_public_routes_and_language` |
| A02 | 未認證者改前端志願者價格 | sandbox 自動檢查通過 | `test_A02_browser_cannot_choose_price` |
| A03 | 同帳號志願者與受助資格 | sandbox 自動檢查通過 | `test_A03_volunteer_and_care_coexist_lowest_price` |
| A04 | 認證到期後付款 | sandbox 自動檢查通過 | `test_A04_expired_verification_requires_requote` |
| A05 | 商城沒有的需求 | sandbox 自動檢查通過 | `test_A05_open_multiple_needs_persist_and_track` |
| A06 | 他人猜測案件 ID | sandbox 自動檢查通過 | `test_A06_guessed_case_and_attachment_are_hidden` |
| A07 | 個案志願者嘗試批准 | sandbox 自動檢查通過 | `test_A07_caseworker_cannot_approve_and_is_audited` |
| A08 | 超區域需求／配送 | sandbox 自動檢查通過 | `test_A08_outside_needs_recorded_delivery_blocked` |
| A09 | 免費援助與有限額度 | sandbox 自動檢查通過 | `test_A09_credit_is_funded_scoped_and_bounded` |
| A10 | 同時兩單搶最後一件 | sandbox 自動檢查通過 | `test_A10_last_item_second_order_rejected` |
| A11 | 取消／到期預留 | sandbox 自動檢查通過 | `test_A11_release_stock_and_credit_once` |
| A12 | 支付回調重送 | sandbox 自動檢查通過 | `test_A12_payment_event_replay_is_idempotent` |
| A13 | 混合現金與支持額度退款 | sandbox 自動檢查通過 | `test_A13_mixed_source_refund_original_sources_and_corporate_adjustment` |
| A14 | 多商家拆單／部分退款 | sandbox 自動檢查通過 | `test_A14_split_by_seller_fulfiller` |
| A15 | 自提碼重複掃描 | sandbox 自動檢查通過 | `test_A15_pickup_single_use` |
| A16 | 淨水器預約 | sandbox 自動檢查通過 | `test_A16_water_booking_has_no_payment_contract` |
| A17 | 代步車 | sandbox 自動檢查通過 | `test_A17_assets_require_inspection_and_receipt` |
| A18 | 義賣和援助共用庫存 | sandbox 自動檢查通過 | `test_A18_purpose_pools_and_restrictions` |
| A19 | 部分援助與候補 | sandbox 自動檢查通過 | `test_A19_partial_aid_counts_only_on_delivery` |
| A20 | 報表卡片點擊與匯出 | sandbox 自動檢查通過 | `test_A20_detail_export_same_filter_and_totals` |
| A21 | 同家庭多次申請 | sandbox 自動檢查通過 | `test_A21_household_dedup_does_not_guess_other_users` |
| A22 | 轉介、預計捐款 | sandbox 自動檢查通過 | `test_A22_referral_and_estimates_are_not_outcomes_or_cash_received` |
| A23 | 商家、倉庫、志願者帳號 | sandbox 自動檢查通過 | `test_A23_roles_are_scoped_at_api` |
| A24 | 公開故事同意未勾選 | sandbox 自動檢查通過 | `test_A24_story_consent_is_optional_and_private` |
| A25 | 缺少付款／通知憑證 | sandbox 自動檢查通過 | `test_A25_unconfigured_external_operations_fail_closed` |
| A26 | 空資料與篩選無結果 | sandbox 自動檢查通過 | `test_A26_empty_and_filtered_views_do_not_fake_data` |
| A27 | 缺口共用供給 | sandbox 自動檢查通過 | `test_A27_shared_supply_cannot_double_allocate` |
| A28 | 資料庫還原 | sandbox 自動檢查通過 | `test_A28_serialization_preserves_relationships` |
| A29 | 惡意附件／表格公式 | sandbox 自動檢查通過 | `test_A29_malicious_upload_rejected_and_excel_escaped` |
| A30 | 時區與報表邊界 | sandbox 自動檢查通過 | `test_A30_new_york_day_bounds_handle_dst` |
| A31 | 管理員新增商品 | sandbox 自動檢查通過 | `test_A31_admin_creates_product_without_code_change` |
| A32 | 新建公益眾籌 | sandbox 自動檢查通過 | `test_A32_campaign_review_publish_and_checkout` |
| A33 | 未審核或停募項目 | sandbox 自動檢查通過 | `test_A33_unapproved_or_paused_cannot_checkout` |
| A34 | 改金額或假成功跳轉 | sandbox 自動檢查通過 | `test_A34_tamper_and_redirect_cannot_mark_success` |
| A35 | 重送支付事件 | sandbox 自動檢查通過 | `test_A35_repeated_donation_event_one_receipt_and_entry` |
| A36 | 部分退款及失敗退款 | sandbox 自動檢查通過 | `test_A36_failed_refund_does_not_reduce_confirmed` |
| A37 | 並發達標、截止後遲到付款 | sandbox 自動檢查通過 | `test_A37_overfund_and_late_success_not_lost` |
| A38 | 公開匿名與資料權限 | sandbox 自動檢查通過 | `test_A38_donor_privacy` |
| A39 | 項目取消 | sandbox 自動檢查通過 | `test_A39_cancel_creates_review_and_notification` |
| A40 | 商品／企業／公眾捐款 | sandbox 自動檢查通過 | `test_A40_sources_remain_separate` |
| A41 | 進度與對帳 | sandbox 自動檢查通過 | `test_A41_reconciliation_expenses_disputes_consistency` |
| A42 | 無正式收款配置 | sandbox 自動檢查通過 | `test_A42_no_live_payments_or_fake_bank_settlement` |

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

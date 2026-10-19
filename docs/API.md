# API

Session authentication + CSRF（`X-CSRFToken`）。所有回應 `{data: ...}` 或 `{error:{code,message}}`。GET 列表 `page`、`page_size`（最大100）；UUID 不提供任何授權能力。非本人記錄回404，不洩漏存在性。敏感 JSON mutation 傳 `Idempotency-Key`，同 actor／URL／key 只執行一次，變更 payload 回409。金融事件另以全域 event_id 去重。

| 介面 | 行為 |
|---|---|
| GET `/api/catalogue/` | q、kind、category、source、max_price 搜尋已公開商品 |
| POST `/api/checkout/quote/` | items:[{product_id,quantity}]、zip、method、可選 grant_id；回 fingerprint、拆單資訊及金額 |
| POST `/api/checkout/create/` | 同 quote 加 fingerprint、地址、Idempotency-Key；重算後交易預留 |
| GET `/api/orders/`、`/:id/` | 自己訂單；必要員工權限可查看，商家使用自己範圍的 orders report |
| POST `/api/orders/:id/cancel/`、`pickup/` | 取消未付款或簽發一次性自提碼（suborder_id） |
| POST `/api/fulfillment/:suborder/` | token（自提）或 tracking（配送確認），商家範圍驗證 |
| POST/GET `/api/help-requests/` | 案件＋needs，支援 draft；未登入資料先儲 session 草稿，登入後提交 |
| GET `/api/help-requests/:id/` | 本人／獲授權個案人員 |
| POST `/api/help-requests/:id/{submit,transition,supplement,note,assign,confirm,grant}/` | 提交草稿、狀態、補件、聯絡紀錄、分派、確認 Need、批准援助 |
| POST/GET `/api/verifications/`；POST `/:id/` | 會員申請；reviewer 人工狀態及期限審核 |
| POST/GET `/api/appointments/`；POST `/:id/` | 區域驗證、純預約、不建立付款 |
| POST `/api/stock/:lot/{adjust,return,transfer}/` | 理由必填、用途限制、檢查隔離及流水 |
| POST `/api/stock/import/` | UTF8 CSV 檔案，lot_id,delta,hold_delta,reason（上限1000筆／1MB） |
| POST `/api/assets/:id/` | inspect/reserve/deliver，免費方案及收件確認 |
| POST `/api/allocations/`、`/:id/` | 已核准計畫與 Need、lot、quantity；交付或 release |
| POST `/api/plans/:id/` | 獨立審核匿名公開摘要 |
| POST `/api/tasks/:id/` | 被指派人更新狀態及時數，另人核准時數 |
| POST `/api/budgets/`、`/api/grants/:id/revoke/` | funded budget、可用餘額撤銷及原來源流水 |
| GET `/api/campaigns/`、`/:id/` | 只列公開及已停募項目，不暴露捐款人姓名或留言 |
| POST `/api/campaigns/:id/{submit,approve,publish,pause,close,cancel,complete}/` | 編輯者與審核者分離、重要政策版本快照 |
| POST `/api/donation-checkout/` | campaign_id、amount_cents、email、receipt_name、policy_version、policy_consent；anonymous 預設true |
| GET `/api/donations/:id/`、`receipt/` | 自己／短效 session 授權／finance；不能猜號讀取 |
| POST `/api/donations/:id/resend/` | finance 重排 sandbox outbox，不真實寄信 |
| POST `/api/refunds/` | donation_id 或 item_id、amount_cents、aid_cents、reason、idempotency_key |
| POST `/api/payment/webhook/` | 自訂 sandbox adapter 協定，非外部支付商原生協定 |
| POST `/api/sandbox/{commerce,public_donation,refund}/:id/` | 僅 sandbox、owner／finance＋CSRF。頁面清楚標示沒有實際金流 |
| POST `/api/finance/reconcile/` | 憑證、fee／settlement／reserve／企業 received，不允許手動偽造公眾成功付款 |
| POST `/api/campaign-expenses/`、`/:id/` | 提交／核准預留／憑證支付／審核公開類別彙總 |
| POST `/api/campaigns/:id/updates/`、`/api/campaign-updates/:id/approve/` | 更新草稿及另人審核 |
| GET `/api/reports/{cases,inventory,orders,donations,finance,tasks,impact}/` | 相同權限與過濾器，回 results/count/totals，日期 created_at、NY 日界 |
| GET 同路徑 `export/` | 同篩選 Excel，公式字串轉義 |
| POST `/api/attachments/` | multipart file＋case_id 或 verification_id，僅本人 |
| GET `/api/attachments/:id/` | 簽發120秒綁使用者 link；`/private/:id/` 再檢查授權 |
| POST `/api/staff/roles/` | admin、current_password、reason，拒絕自己改自己角色 |

商品、商家、幫扶計畫、任務及眾籌的新增編輯透過 CSRF 保護的 HTML 後臺 `/admin/.../?new=1` 與 `/admin/.../:uuid/`。這是完整伺服器表單，不需要修改程式才能操作。

## Sandbox webhook envelope

JSON：`{event_id,purpose,reference,kind,amount_cents}`；purpose 分 commerce／public_donation／refund。公眾捐款爭議事件 kind 為 dispute_open／dispute_lost／dispute_won／dispute_restored，另含 dispute_id。

Header `X-Keran-Timestamp` 為 Unix 秒，`X-Keran-Signature = HMAC-SHA256(WEBHOOK_SECRET, timestamp + '.' + 原始body)`，有效窗300秒。簽名錯誤、時間過期、金額不符、事件 payload 衝突一律拒絕。此協定只驗證本系統 sandbox 接入邊界，不宣稱是 Stripe/PayPal 官方驗簽實作。

# 資料字典及業務規則

業務實體使用 UUID、created_at、updated_at、version。帳號沿用 Django User 整數主鍵，業務外鍵使用 PROTECT 防止破壞交易歷史。所有金額 USD 美分整數；日期 UTC，頁面和日界 America/New_York。Django migrations 是資料結構的權威來源。

| 模組 | 實體及關係 |
|---|---|
| 身分 | User ↔ Group（員工角色），Household ↔ User，Verification → User，StaffMFA → User |
| 商品 | Organization（merchant／organization）、Product（V1 每商品一個庫存 SKU、含單位及規格）、Lot（商品／擁有方／倉庫／倉位／批次／用途）、Asset（逐臺資產） |
| 求助 | Case → User／Household／Assignee；Need → Case；Consent、Note、Attachment → Case 或 Verification |
| 援助 | Budget → Grant → AidLedger；Grant → User／Case／Reviewer，限制商品及品類；Plan ↔ Need；Allocation → Need／Reservation／Plan |
| 庫存 | Reservation → Lot／Order，StockMovement → Lot；所有進出、預留與釋放追加流水 |
| 商城 | Order → Suborder（商家＋履約方）→ Item（價格／規則快照）；Pickup 使用 token SHA256 雜湊及一次性 used_at |
| 服務 | Appointment；Task（跟進／時數，審核時數不等於價值排名） |
| 眾籌 | Campaign → PolicyVersion；Donation → Campaign／政策快照；Receipt → Donation；Refund、Dispute、FinanceEntry、Expense、CampaignUpdate |
| 基礎 | Outbox、Audit、Setting、Mutation（敏感 API 的冪等快取，僅存 payload digest）、LoginAttempt（限流） |

## 定價
公開價格、有效志願者價及有效關懷價中取最低，不疊加。資格檢查使用現在時間；`quote.fingerprint` 納入完整報價、商品版本及可用資格。建立訂單時重新計算，不一致回 `requote`，不偷偷變更扣款。

額度 available = granted − reserved − redeemed − revoked。支持額度僅抵授權商品折後金額，不抵運費／稅，不換現。免費物資走援助用途池及核准件數；零現金訂單直接記核准內部訂單，不呼叫支付。額度批准預留 funded budget；無資金不得發出可用額度。家庭重複方案需要人工例外原因。

## 庫存
available = on_hand − reserved − hold。DB 約束禁止負數；預留以 IMMEDIATE SQLite 寫入交易／PostgreSQL row lock、條件 UPDATE 執行。普通訂單預留預設15分鐘；援助資源預留預設7天（`aid_reservation_days`）。jobs 重跑只釋放一次。實際交付才扣 on_hand。退貨先增加 hold，檢查後人工放行；受限捐贈禁止用途移轉。不同單位不相加，未定換算不提供自動換算。五臺報告數量僅資產待盤點，不算可售庫存。

## 需求數量與報表
requested ≥ confirmed ≥ allocated ≥ fulfilled。計畫關聯原 Need，不複製個案或需求。分配先增 allocated，實際交付才增 fulfilled，釋放減 allocated。confirmed − allocated 是未安排缺口，confirmed − fulfilled 是未交付。過期候補（30天未人工確認）不計有效可分配缺口。不同品類／單位分列。家庭按 Household ID 去重，同帳號沿用同家庭，不因相同地址或名字自動合併不同人。

案件 received → reviewing → matching → arranged → completed；needs_info／waitlisted／referred／declined／withdrawn 為輔助狀態。轉換須理由，referred 不算完成；審核員不可審自己的案件。完成前檢查已確認需求已交付。個案人員只讀被分派或自己的案件，不能批准援助。

## 商城財務
Order 的 payment_status、fulfillment_status、refund_status 分開。商家按自己 Suborder 處理，報表遮罩支持來源，不得查看受助身份或證明；只提供必要的商品、交付地址與聯絡範圍。商品淨款、企業捐款、公眾捐款分 bucket。

企業預計捐款 = 合資格現金淨商品款 × bps / 10000 ＋ 每件固定額。稅、運費、支持資金不計基數；退款按相關明細現金比例沖銷。estimated／adjusted 不是 received；received 須財務輸入收款憑證、外部參照及原因。尚未提供自動商家付款或既有倉庫 API。

## 眾籌財務
Donation 金額及政策版本由伺服器確認。只有可信測試事件成功才入帳，瀏覽器回跳不算成功。同 event_id 的 payload 不同拒絕；已處理事件不重複入帳或收據。

公開 confirmed = succeeded gross − confirmed refunds − lost chargebacks + restored chargebacks（chargeback_cents 表示淨損失）。未結案爭議另列，凍結可支用但不先扣公開 confirmed。超募保留實際百分比，視覺上限100%。達標後停止新 checkout，已建立的付款成功仍入帳。停募／截止後成功會 needs_review，依原政策退款或執行。

內部 spendable = settlement − paid expense − approved expense reservation − 手工必要準備金 − approved pending refunds − confirmed refunds − lost chargebacks − open dispute。settlement 定義為已扣費、尚未沖銷退款／拒付本金的結算入帳；退款／拒付本金由獨立流水扣除。fee 另列，不再次扣 fee。若銀行淨額已含退款／拒付，對帳須拆解成結算及各沖銷來源，不能整筆淨額再重扣本金。現有程式提供人工憑證對帳，不聲稱支付成功等於銀行已到帳。退款需核准並等可信事件，失敗不改 confirmed。收據為測試確認文字文件，不聲稱抵稅。

## 安全與保留
CSRF、session HttpOnly、SameSite、輸出轉義、CSP、登入限流、短效私人下載、角色與 owner scope、正式 staff TOTP、不可變交易入口。附件僅接受最多5MB PNG/JPEG，解碼再編碼去除主動內容／metadata；不接收 PDF／SVG／Office。文件存私人目錄，下載 link 120秒且綁定登入使用者，每次重新檢查權限。公眾捐款訪客 session 存取30分鐘，登入者可讀自己的歷史。

附件保留期需管理員設定；新附件依設定 retain_until，jobs 到期刪除內容並保留清理稽核。用戶個資刪除與法定財務保留目前由管理程序處理，未提供自助匿名化 UI。財務、庫存、稽核採追加／沖銷，不能透過後臺任意改歷史餘額。

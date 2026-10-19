# 實施基線
附件為產品需求輸入。以使用者明確授權的完整 V1.0 為目標；公開發布、真實付款和真實通知不包含在本次授權中。

## 架構
Django 5.2 LTS：服務端 HTML + 漸進 JavaScript、ORM、CSRF、session、權限。預覽 SQLite（持久化，IMMEDIATE 寫入交易）；部署 PostgreSQL。所有業務識別 UUID，金額 USD 美分整數，UTC 時間，紐約報表日界。

## 資料關係
User ↔ Group；User → Household、Verification、Case → Need；Case → Grant → AidLedger；Product → Lot → StockMovement/Reservation；Order → Suborder → Item；Campaign → PolicyVersion/Donation → Ledger/Receipt/Refund/Dispute；Plan ↔ Need → Allocation；Attachment、Consent、Task、Outbox、Audit 提供跨域支援。

## 階段
1. 模型、遷移、角色及隔離 seed。
2. 核心交易：權限、狀態、庫存、額度、拆單、付款事件、退款、公開捐款。
3. 雙語公共頁、會員流程、管理工作臺和報表。
4. 自動化 API/交易與瀏覽器驗收、還原驗證。
5. 部署、管理與逐項驗收紀錄。未實作或未驗證項必須清楚標示。

## 安全邊界
商品／合作條件草稿；正式支付 fail closed；sandbox 不代表收款。後臺權限在伺服器強制；私人檔案不在靜態目錄。角色與會員資格獨立。所有重要變更追加稽核，財務及庫存交易不可透過一般 CRUD 直接改寫。

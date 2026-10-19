# 審閱預覽

這是有持久資料、權限和交易流程的網站，不是只有截圖；截圖取自 Chromium 操作實際 Django 服務的測試。

- [桌面首頁](../artifacts/home-desktop.png)
- [手機繁中首頁](../artifacts/home-mobile-zh.png)
- [公益眾籌詳情](../artifacts/campaign.png)
- [管理工作中心](../artifacts/work-centre.png)
- [可離線開啟的截圖審閱頁](../artifacts/preview.html)（僅截圖索引，不冒充可操作網站）

互動服務於本雲端的8000埠運行，使用隔離的 `var/demo`。本平台沒有提供可用的公開網站預覽轉發工具，因此沒有可分享的公共網址，也沒有公開部署；在支援埠轉發的開發工具連到8000，或在本機依 README 啟動即可審閱實際互動。

測試角色和隨機密碼取得方式見 README。不要把 `var/demo/review-accounts.json` 分享到公共頁面。建議順序：會員購物／求助 → 審核員認證／評估 → 管理員計畫 → 倉庫交付 → 財務退款／對帳。也可直接跑 `scripts/browser_review.py` 重現完整流程。

未知真實商品、合作條件、稅務、服務範圍及法律資料不因審閱而自動批准；正式啟用條件見 LAUNCH.md。

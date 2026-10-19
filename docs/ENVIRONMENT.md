# 雲端重啟與自動設定

目前8000埠的預覽已用 `sh scripts/start-preview.sh` 啟動。程序本身不會隨環境快照保留；需要在新任務重啟。沿用現有 checkout，每個雲端任務本來已隔離，不要另建 Git worktree，除非使用者明確要求。

本次嘗試把 install_script 與 start_skill 存入雲端環境設定，服務回 `INVALID_ARGUMENT`，未確認儲存成功。重新讀取顯示兩欄仍為 null，所以**不能宣稱雲端自動啟動設定已保存或發布**。所有必要步驟已保存在 README、scripts/setup.sh 及 scripts/start-preview.sh，可在環境設定中手動填入以下內容。這不是權限拒絕，不需要提供秘密或重複 GitHub token。

安裝：
```sh
cd /workspace/keran-platform
sh scripts/setup.sh
```

開始預覽：
```sh
cd /workspace/keran-platform
sh scripts/start-preview.sh
```

檢查根頁、/shop/、/help/、/fundraising/、/login/ 及已標示測試商品的 catalogue API。`var/demo` 與 `var` 都是持久資料，不能重置；測試帳號隨機密碼只從該環境0600檔案私密讀取。不要把 loopback 位址當成公共預覽連結。正式收款與通知仍停用。

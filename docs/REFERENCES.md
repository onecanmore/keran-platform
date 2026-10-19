# 官方資料查核

開發時實際讀取 Django 官方 stable/5.2.x 文件：
- [Python 相容性](https://github.com/django/django/blob/stable/5.2.x/docs/faq/install.txt)：Django 5.2 支援本機 Python 3.12。
- [資料庫與 SQLite transaction_mode](https://github.com/django/django/blob/stable/5.2.x/docs/ref/databases.txt)：IMMEDIATE 模式、鎖等待和交易時間建議。本應用採短範圍交易與30秒 timeout，並做實際雙連線驗證。
- [Django CSRF](https://docs.djangoproject.com/en/5.2/ref/csrf/) 及 [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)：由已安裝 Django 5.2.13 執行 `check --deploy`，另做直接 CSRF 拒絕及權限測試。

套件從官方 PyPI／npm TLS 路線下載，未關閉憑證、簽章或校驗。完整版本見 requirements，實際執行結果見驗收文件。沒有正式第三方支付供應商接入，不能以自訂 sandbox HMAC 協定宣稱已完成支付商官方整合。

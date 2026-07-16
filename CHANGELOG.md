# Changelog

本檔案記錄 Open Mail Room 每個版本的變更。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/),版號遵循 [語意化版本](https://semver.org/lang/zh-TW/)。

## [1.0.0] - 2026-07-16

首次公開發布。

### 新增

- **收件登錄**:手機拍照(PWA)、批次上傳(單批最多 30 張)、條碼/QR 掃描帶入單號、HEIC 支援
- **AI OCR**:辨識收件人/寄件人/單號/承運商/COD 金額;低信心欄位標示待人工確認。支援 OpenAI、Anthropic Claude、Google Gemini、OpenRouter、本地 Ollama,可設多家優先度並自動故障轉移
- **拍照時間**:自 EXIF 取出 DateTimeOriginal 並保存顯示;GPS 等其餘 EXIF 於入口剝除
- **收件人比對**:中文姓名模糊比對(含別名);部門件自動比對部門並通知該部門固定聯絡人
- **通知**:Email、LINE、Slack、Discord、Telegram、自訂 Webhook(HMAC 簽章);員工自助綁定、催領排程、失敗重試與死信清單
- **領取**:取件碼查詢、螢幕簽名存證、代領記錄;機密件限定角色並記錄每次檢視
- **交寄**:交寄單、託運單號登錄(可拍照 OCR)、寄出通知
- **報表**:期間統計、部門/承運商/日別分組、CSV 匯出
- **管理**:角色權限(admin/counter/employee/viewer)、員工名錄 CSV 匯入、部門管理、使用者管理(新增時寄送歡迎信)、稽核軌跡查詢、AI 設定、Webhook 端點管理
- **離線**:斷線時登錄排入佇列,恢復連線自動送出
- **保存期限**:到期自動匿名化
- **客製**:`config/branding.yaml` 調整品牌、主色、取件地點、保存年限、通知範本與功能開關,免改程式
- **多語**:繁體中文、English

### 安全

- 個資欄位 AES-256-GCM 加密存放,支援金鑰輪替(版本前綴)
- 上傳照片與簽名檔加密後落地
- 照片入口剝除 EXIF(GPS 屬個資)
- argon2id 密碼雜湊
- 上傳魔數驗證、Pillow 重新編碼消毒、解壓縮炸彈防護、單檔 15MB / 單批 30 張上限
- CSRF double-submit token、HttpOnly session cookie
- Webhook 與自架 AI 端點的 SSRF 防護(預設拒連內網)
- 生產環境拒絕以弱金鑰啟動

[1.0.0]: https://github.com/YOUR-USERNAME/open-mail-room/releases/tag/v1.0.0

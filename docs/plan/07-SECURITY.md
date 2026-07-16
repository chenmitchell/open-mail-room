# 07 資訊安全規格(全程強制遵守)

## 1. 傳輸加密

- 一律 HTTPS:Docker Compose 內建 Caddy 反向代理,自動申請/續期 Let's Encrypt 憑證;無網域的內網環境提供自簽憑證腳本與說明。
- HSTS(max-age 1 年)、HTTP 一律 301 到 HTTPS;TLS ≥1.2(建議 1.3)。
- 相機 getUserMedia 本來就要求 secure context,HTTPS 是硬需求非加分項。
- 對外 webhook 僅允許 https:// URL(可設定放行內網 http,預設關)。

## 2. 認證與授權

- 密碼:argon2id;登入速率限制 + 失敗鎖定(5 次/15 分);可選 TOTP 2FA。
- Session:HttpOnly + Secure + SameSite=Lax cookie;JWT 15 分 + refresh 輪替;登出撤銷。
- RBAC 在後端每個端點強制檢查(不能只靠前端隱藏按鈕);employee 只能查自己的件。
- API Key:只存 hash;scopes 最小權限;可設到期日;每次使用記 last_used。

## 3. 靜態資料加密(at rest)

分層策略(在「安全」與「自架者可用性」間取捨,理由記入 DECISIONS):

1. **欄位級加密(應用層)**:個資與秘密欄位——employees.email/phone、sender_phone、to_address/to_phone、notification_bindings.address、ai_provider_configs.api_key_encrypted、webhook secret、totp_secret——用 AES-256-GCM 加密後入庫。金鑰 `OPENMAILROOM_ENCRYPTION_KEY` 由 `.env` 提供(安裝腳本自動產生 32 bytes random),支援金鑰輪替(密文帶 key version)。
2. **檔案儲存**:照片/簽名檔以 AES-256-GCM 加密後落地(檔名用 UUID,不含個資),讀取時經授權端點串流解密;不可直接以靜態檔案伺服。
3. **整庫加密(可選)**:文件說明如何用 LUKS/BitLocker 加密 volume,或 PostgreSQL + 磁碟加密;SQLite 使用者可選 SQLCipher(提供 build flag,預設不強制以免依賴複雜)。
4. **備份加密**:每日備份以 age/GPG 加密後才落地或上傳 S3。

> 明確警告文件化:`OPENMAILROOM_ENCRYPTION_KEY` 遺失=個資欄位與照片永久無法解密;備份 key 的方式寫進安裝指南。

## 4. 上傳安全

- 僅允許 image/jpeg、image/png、image/webp、image/heic;魔數(magic bytes)驗證,不信任副檔名與 Content-Type。
- 單檔 ≤15MB、單批 ≤30 張;以 Pillow 重新編碼(去 EXIF——EXIF 有 GPS 位置屬個資,同時消毒潛在惡意 payload)。
- 上傳目錄 noexec;回應一律 `Content-Disposition` 與正確 MIME,防 XSS via SVG(SVG 不在白名單)。

## 5. 應用安全基線

- ORM 參數化(禁字串拼 SQL);Pydantic 驗證所有輸入;輸出跳脫(Vue 預設)+ CSP(default-src 'self')、X-Content-Type-Options、Referrer-Policy。
- SSRF 防護:webhook/base_url 等使用者可填的 URL,解析後禁私有網段(169.254.、10.、172.16-31.、192.168.、localhost),除非 admin 明示放行。
- 秘密不進 log;log 遮罩姓名以外個資;錯誤回應不洩 stack trace。
- 依賴供應鏈:鎖版本(uv lock / package-lock)、CI 跑 `pip-audit` + `npm audit` + `bandit` + `ruff`;Docker image 用 slim/non-root user、唯讀 rootfs、healthcheck。
- CORS:預設同源;API 串接方明確設定白名單。
- 個資法對齊:蒐集告知文案範本(登入頁/員工首次使用)、保存期限自動化(02)、稽核紀錄(02)、資料當事人查詢/刪除的 admin 操作。

## 6. 穩定性要求(使用者明示「系統要求穩」)

- 所有背景工作冪等 + 重試 + 死信;OCR/通知失敗不影響主流程(可手動補)。
- `/healthz`、`/readyz`、結構化 JSON log、可選 Prometheus metrics;compose `restart: unless-stopped`。
- 每日 DB + 檔案備份,保留 14 份滾動;文件含還原演練步驟(備份沒演練過=沒有備份)。
- 升級策略:Alembic migration 前自動備份;版本號 semver;CHANGELOG。

## 7. 威脅模型摘要(執行時針對每項寫測試)

| 威脅 | 對策 |
|---|---|
| 櫃台裝置遺失 | session 短效 + 可遠端登出全部裝置 |
| 內部人員窺探機密件 | 機密件照片/寄件人需 admin 或收件人本人;查看留稽核 |
| API key 外洩 | scope 最小化、到期、輪替、速率限制、稽核 |
| Webhook 偽造 | HMAC + 時間窗防重放(03 §3) |
| AI 服務商資料外流 | 影像壓縮去 EXIF、機密件禁 AI、支援本地 Ollama |
| 惡意上傳 | §4 全套 |
| 暴力破解 | argon2id + 鎖定 + 2FA |

# 03 API 規格

FastAPI 自動產出 OpenAPI 3.1(`/api/docs`)。所有路徑前綴 `/api/v1`。回應統一 `{ "data": ..., "error": null }` / `{ "data": null, "error": { "code", "message" } }`。分頁用 `?page=&size=`,回 `meta: { total, page, size }`。

## 1. 認證

- 網頁/PWA:登入 `POST /auth/login` → HttpOnly Secure Cookie(session JWT,15 分鐘)+ refresh token 輪替;CSRF token(double submit)。
- 第三方串接:`Authorization: Bearer <api_key>`;key 帶 scopes:`items:read`、`items:write`、`employees:read`、`employees:write`、`webhooks:manage`、`reports:read`。
- 速率限制:登入 5 次/分/IP;API 依 key 設定(預設 60 req/min)。

## 2. 端點總表

### 收件
- `POST /items` 建立(人工或確認 OCR 後)
- `GET /items` 查詢(q、status、carrier_id、department_id、date_from/to、confidential)
- `GET /items/{id}` / `PATCH /items/{id}`(狀態變更走專用端點)
- `POST /items/{id}/pickup` 領取核銷 `{ method, picked_up_by_name, signature_png_base64? | pickup_code? }`
- `POST /items/{id}/return` / `POST /items/{id}/forward`
- `POST /items/{id}/notify` 手動重发通知

### 照片與 OCR
- `POST /uploads` multipart,批次 ≤30 張,回 attachment ids(驗證規則見 07 §4)
- `POST /ocr/jobs` `{ attachment_ids: [...] }` → 逐張排 OCR,回 job ids
- `GET /ocr/jobs/{id}` 輪詢;或 `GET /ocr/stream`(SSE)推進度
- OCR 結果為「草稿」:`GET /ocr/jobs/{id}/draft` 回預填欄位 + 員工比對候選 `{ employee_id, score }[]`;櫃台確認後才 `POST /items`

### 交寄
- `POST /outbound` / `GET /outbound` / `PATCH /outbound/{id}`
- `POST /outbound/{id}/shipped` `{ tracking_no?, attachment_id? }`

### 名錄與部門
- `GET|POST|PATCH /employees`、`POST /employees/import`(CSV)、`GET /employees/match?q=`(模糊比對,前端確認頁用)
- `GET|POST|PATCH /departments`

### 通知綁定(員工自助)
- `POST /me/bindings/line/start` → 回綁定碼;員工加 LINE 官方帳號後輸入綁定碼,webhook 收到後完成綁定(流程見 05)
- `POST /me/bindings/{channel}` / `DELETE /me/bindings/{id}`

### 管理
- `GET|PUT /admin/settings`、`GET|POST /admin/ai-providers`(key 只寫不讀,回遮罩 `sk-***abc`)
- `GET|POST|DELETE /admin/api-keys`、`GET|POST|PATCH /admin/webhooks`、`POST /admin/webhooks/{id}/test`
- `GET /admin/audit-logs`
- `GET /reports/summary?from=&to=&group_by=department|carrier|day`
- `GET /exports/items.csv|xlsx`

### 系統
- `GET /healthz`(liveness)、`GET /readyz`(DB/queue 檢查)、`GET /metrics`(Prometheus,可關)

## 3. 對外 Webhook(系統 → 訂閱者)

事件:`item.received`、`item.notified`、`item.reminder`、`item.picked_up`、`item.returned`、`item.unclaimed`、`outbound.shipped`

Payload:
```json
{
  "event": "item.received",
  "id": "evt_...",
  "occurred_at": "2026-07-09T10:00:00+08:00",
  "data": {
    "item_no": "IN-20260709-0012",
    "tracking_no": "70012345678",
    "carrier": "tcat",
    "recipient": { "employee_id": "...", "name": "王小明", "department": "行銷部" },
    "status": "received",
    "confidential": false
  }
}
```
- 機密件:payload 隱藏 sender 與照片連結。
- 簽章:`X-Open Mail Room-Signature: t=<unix>,v1=HMAC_SHA256(secret, t + "." + body)`;接收方須驗簽 + 5 分鐘時間窗防重放。
- 重試:5xx/timeout 指數退避 5 次;連續失敗 20 次自動停用並通知 admin。

用途範例:公司自有系統收到 `item.received` 後,自行推 LINE/內部 IM 給收件人——即使不用內建通知模組也能整合。

## 4. 錯誤碼(節錄)
`AUTH_INVALID`、`AUTH_RATE_LIMITED`、`UPLOAD_TOO_LARGE`、`UPLOAD_BAD_TYPE`、`OCR_PROVIDER_DOWN`、`OCR_BUDGET_EXCEEDED`、`EMPLOYEE_AMBIGUOUS`、`PICKUP_CODE_INVALID`、`ITEM_ALREADY_PICKED`

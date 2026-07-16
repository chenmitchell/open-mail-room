# API 串接指南

本文件供第三方開發者將 Open Mail Room 系統整合至自有系統。所有 API 端點前綴為 `/api/v1`，採用統一的 JSON 回應格式。

## 1. 認證方式

### 網頁 / PWA 登入

通過 `POST /auth/login` 進行登入，回傳 HttpOnly Secure Cookie：
- **session JWT** (15 分鐘有效期)
- **CSRF token** (雙重送出驗證)

登入請求：
```json
{
  "email": "user@example.com",
  "password": "password"
}
```

登入回應：
```json
{
  "data": {
    "id": "usr_xxxxx",
    "email": "user@example.com",
    "display_name": "王小明",
    "role": "counter",
    "is_active": true
  },
  "error": null
}
```

**速率限制**：同一 IP 登入失敗逾 5 次/分鐘則被鎖定，返回 HTTP 429。

### 第三方 API 密鑰認證

第三方應用可透過 API key 進行無狀態認證。在 HTTP Header 傳送：
```
Authorization: Bearer <api_key>
```

API key 由管理後台產生，包含以下 scopes：
- `items:read` — 讀取收件項目
- `items:write` — 建立/修改收件項目
- `employees:read` — 讀取員工名錄
- `employees:write` — 新增/修改員工
- `webhooks:manage` — 管理 webhook 訂閱
- `reports:read` — 讀取報表

**速率限制**：每個 API key 預設 60 個請求/分鐘，可在管理後台調整。

## 2. 統一回應格式

所有回應遵循以下格式：

### 成功回應

```json
{
  "data": {
    ...response fields...
  },
  "error": null
}
```

### 錯誤回應

```json
{
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message"
  }
}
```

### 分頁回應

使用 `?page=<num>&size=<size>` 進行分頁，回應包含：
```json
{
  "data": [...items...],
  "error": null,
  "meta": {
    "total": 1250,
    "page": 2,
    "size": 50
  }
}
```

## 3. 主要端點速查表

### 收件管理

| 方法 | 路徑 | 說明 | 需要權限 |
|------|------|------|---------|
| POST | `/items` | 建立收件項目 | `items:write` |
| GET | `/items` | 查詢收件項目(支援篩選、分頁) | `items:read` |
| GET | `/items/{id}` | 取得單筆收件項目 | `items:read` |
| PATCH | `/items/{id}` | 修改收件項目欄位 | `items:write` |
| POST | `/items/{id}/pickup` | 標記為已領取(需簽名或取件碼) | `items:write` |
| POST | `/items/{id}/return` | 標記為已退回 | `items:write` |
| POST | `/items/{id}/forward` | 標記為已轉寄 | `items:write` |
| POST | `/items/{id}/notify` | 手動重發通知給收件人 | `items:write` |

### 照片與 OCR

| 方法 | 路徑 | 說明 | 需要權限 |
|------|------|------|---------|
| POST | `/uploads` | 上傳照片(multipart, ≤30 張) | `items:write` |
| POST | `/ocr/jobs` | 啟動 OCR 任務 | `items:write` |
| GET | `/ocr/jobs/{id}` | 輪詢 OCR 結果 | `items:read` |
| GET | `/ocr/jobs/{id}/draft` | 取得 OCR 預填欄位與員工候選 | `items:read` |

### 員工與部門

| 方法 | 路徑 | 說明 | 需要權限 |
|------|------|------|---------|
| GET | `/employees` | 列出所有員工 | `employees:read` |
| POST | `/employees` | 新增員工 | `employees:write` |
| PATCH | `/employees/{id}` | 修改員工資訊 | `employees:write` |
| POST | `/employees/import` | 批量匯入員工 (CSV) | `employees:write` |
| GET | `/employees/match?q=keyword` | 模糊比對員工姓名 | `employees:read` |
| GET | `/departments` | 列出所有部門 | `employees:read` |
| POST | `/departments` | 新增部門 | `employees:write` |

### 通知綁定 (員工自助)

| 方法 | 路徑 | 說明 | 認證方式 |
|------|------|------|---------|
| POST | `/me/bindings/line/start` | 啟動 LINE 綁定流程 | Session/API key |
| POST | `/me/bindings/{channel}` | 手動綁定通知管道 | Session |
| DELETE | `/me/bindings/{id}` | 移除通知綁定 | Session |

### 管理後台

| 方法 | 路徑 | 說明 | 需要權限 |
|------|------|------|---------|
| GET | `/admin/settings` | 取得系統設定 | admin |
| PUT | `/admin/settings` | 修改系統設定 | admin |
| GET | `/admin/ai-providers` | 列出 AI 提供商設定 | admin |
| POST | `/admin/ai-providers` | 新增 AI 提供商 | admin |
| DELETE | `/admin/api-keys/{id}` | 撤銷 API 密鑰 | admin |
| GET | `/admin/webhooks` | 列出 webhook 端點 | admin |
| POST | `/admin/webhooks` | 新增 webhook 訂閱 | admin |
| POST | `/admin/webhooks/{id}/test` | 測試 webhook | admin |
| GET | `/admin/audit-logs` | 查看稽核日誌 | admin |
| GET | `/reports/summary` | 統計摘要(可按部門/承運商/日期分組) | reports:read |
| GET | `/exports/items.csv` 或 `.xlsx` | 匯出收件清單 | reports:read |

### 系統健檢

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/healthz` | Liveness probe (簡單狀態檢查) |
| GET | `/readyz` | Readiness probe (檢查資料庫、隊列) |
| GET | `/metrics` | Prometheus 監控指標 |

## 4. 建立收件項目範例

### 手動輸入（無 OCR）

```bash
curl -X POST https://mailroom.example.com/api/v1/items \
  -H "Authorization: Bearer sk_live_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_no": "2207123456789",
    "carrier_id": "tcat",
    "mail_type": "parcel",
    "sender_name": "ABC 物流",
    "sender_org": "ABC Co.",
    "recipient_employee_id": "emp_12345",
    "recipient_name_raw": "王小明",
    "is_confidential": false,
    "is_cod": false,
    "refrigeration": "none"
  }'
```

### 從 OCR 確認後建立

OCR 工作流程：
1. `POST /uploads` 上傳照片，取得 `attachment_id[]`
2. `POST /ocr/jobs` 啟動 OCR，取得 `job_id`
3. 輪詢 `GET /ocr/jobs/{job_id}` 直到完成
4. `GET /ocr/jobs/{job_id}/draft` 取得預填欄位，展示給使用者確認
5. 使用者修正後，`POST /items` 建立正式記錄，傳入 `ocr_job_id` 與 `attachment_ids`

```bash
# 步驟 3-5：建立項目，連結 OCR 結果
curl -X POST https://mailroom.example.com/api/v1/items \
  -H "Authorization: Bearer sk_live_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "ocr_job_id": "ocr_xxx",
    "attachment_ids": ["att_1", "att_2"],
    "tracking_no": "2207123456789",
    "carrier_id": "tcat",
    "recipient_employee_id": "emp_12345",
    "recipient_name_raw": "王小明"
  }'
```

## 5. 對外 Webhook 訂閱

第三方可訂閱 Open Mail Room 系統事件，系統會以 HTTP POST 推送通知。此功能讓您自行整合到公司內部系統或 IM，無需依賴內建通知模組。

### 事件類型

系統會推送以下事件：

| 事件 | 觸發時機 | 說明 |
|------|---------|------|
| `item.received` | 收件項目建立 | 新的郵件/包裹已登記 |
| `item.notified` | 通知已發送 | 通知已傳給收件人 |
| `item.reminder` | 提醒通知 | 超過 N 天未領時的提醒 |
| `item.picked_up` | 已領取 | 收件人或代理人已領取 |
| `item.returned` | 已退回 | 郵件已標記為退回 |
| `item.unclaimed` | 未領超期 | 超過保留期限未領 |
| `outbound.shipped` | 交寄已出貨 | 交寄單已由承運商接收 |

### Webhook Payload 範例

```json
{
  "event": "item.received",
  "id": "evt_20260709001",
  "occurred_at": "2026-07-09T10:00:00+08:00",
  "data": {
    "item_no": "IN-20260709-0012",
    "tracking_no": "70012345678",
    "carrier": "tcat",
    "recipient": {
      "employee_id": "emp_123",
      "name": "王小明",
      "department": "行銷部"
    },
    "status": "received",
    "confidential": false,
    "sender_name": "ABC 物流",
    "sender_org": "ABC Co.",
    "received_at": "2026-07-09T10:00:00+08:00"
  }
}
```

**注意**：如果項目標記為機密件 (`confidential: true`)，payload 將隱藏 `sender_name`、`sender_org` 等寄件人資訊。

### 簽章驗證

每個 webhook 請求皆包含 HMAC SHA256 簽章，防止偽造。

**Header**：
```
X-Open Mail Room-Signature: t=<unix_timestamp>,v1=<hmac_sha256>
```

**驗簽步驟**：

1. 從 Header 取出 `t` (時間戳) 與 `v1` (簽章)
2. 驗證時間戳在 5 分鐘內（防重放）
3. 用訂閱時設定的 `secret` 計算簽章

#### Python 範例

```python
import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone

def verify_webhook_signature(
    request_body: str,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300
) -> bool:
    """驗證 webhook 簽章"""
    parts = signature_header.split(',')
    timestamp = None
    signature = None
    
    for part in parts:
        key, value = part.split('=', 1)
        if key.strip() == 't':
            timestamp = int(value)
        elif key.strip() == 'v1':
            signature = value
    
    if not timestamp or not signature:
        return False
    
    # 檢查時間戳
    now = datetime.now(timezone.utc).timestamp()
    if abs(now - timestamp) > tolerance_seconds:
        return False
    
    # 驗證簽章
    message = f"{timestamp}.{request_body}"
    expected_sig = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_sig)

# 使用範例
@app.post("/webhook/mailroom")
def handle_webhook(request: Request):
    body = request.body.decode()
    sig_header = request.headers.get("X-Open Mail Room-Signature", "")
    secret = "whk_secret_xxxxx"  # 訂閱時取得
    
    if not verify_webhook_signature(body, sig_header, secret):
        return {"error": "Invalid signature"}, 401
    
    payload = json.loads(body)
    # 處理事件
    return {"status": "ok"}
```

#### Node.js 範例

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(
  requestBody,
  signatureHeader,
  secret,
  toleranceSeconds = 300
) {
  // 解析 Header
  const parts = signatureHeader.split(',');
  let timestamp = null;
  let signature = null;
  
  for (const part of parts) {
    const [key, value] = part.split('=');
    if (key.trim() === 't') {
      timestamp = parseInt(value);
    } else if (key.trim() === 'v1') {
      signature = value;
    }
  }
  
  if (!timestamp || !signature) {
    return false;
  }
  
  // 檢查時間戳
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > toleranceSeconds) {
    return false;
  }
  
  // 驗證簽章
  const message = `${timestamp}.${requestBody}`;
  const expectedSig = crypto
    .createHmac('sha256', secret)
    .update(message)
    .digest('hex');
  
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expectedSig)
  );
}

// 使用範例（Express）
app.post('/webhook/mailroom', (req, res) => {
  const body = req.rawBody; // 需要設定 express.raw()
  const sigHeader = req.headers['x-openmailroom-signature'];
  const secret = 'whk_secret_xxxxx';
  
  if (!verifyWebhookSignature(body, sigHeader, secret)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }
  
  const payload = JSON.parse(body);
  // 處理事件
  res.json({ status: 'ok' });
});
```

### 重試機制

- **自動重試**：系統在收到 5xx 狀態碼或超時時，採用指數退避策略重試最多 5 次
- **連續失敗**：同一端點連續失敗 20 次後，系統自動停用該 webhook 並通知管理員
- **恢復**：管理員可手動重新啟用或測試 webhook (`POST /admin/webhooks/{id}/test`)

### 建立 Webhook 訂閱

```bash
curl -X POST https://mailroom.example.com/api/v1/admin/webhooks \
  -H "Authorization: Bearer sk_live_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "內部系統通知",
    "url": "https://internal-system.example.com/webhooks/mailroom",
    "secret": "whk_xxxxx",
    "events": ["item.received", "item.picked_up", "outbound.shipped"],
    "is_active": true
  }'
```

## 6. 常見錯誤碼

| 錯誤碼 | HTTP 狀態 | 說明 | 處理建議 |
|--------|---------|------|---------|
| `AUTH_INVALID` | 401 | 登入失敗或 API key 無效 | 檢查認證資訊 |
| `AUTH_RATE_LIMITED` | 429 | 登入或 API 請求超過速率限制 | 等待後重試（指數退避） |
| `UPLOAD_TOO_LARGE` | 413 | 上傳檔案超過大小限制 | 減小檔案大小或分批上傳 |
| `UPLOAD_BAD_TYPE` | 400 | 上傳檔案格式不符 | 確認檔案為有效圖片或 base64 |
| `OCR_PROVIDER_DOWN` | 503 | AI OCR 服務商暫時無法使用 | 自動 failover；或讓使用者手動輸入 |
| `OCR_BUDGET_EXCEEDED` | 402 | AI 服務商月預算已用完 | 聯絡管理員增加預算或切換提供商 |
| `EMPLOYEE_NOT_FOUND` | 404 | 收件人員工 ID 不存在 | 確認員工是否已建立 |
| `EMPLOYEE_AMBIGUOUS` | 422 | 員工模糊比對結果過多 | 在確認頁讓使用者選擇 |
| `PICKUP_CODE_INVALID` | 422 | 取件碼錯誤或不匹配 | 檢查取件碼並重試 |
| `ITEM_ALREADY_PICKED` | 409 | 項目已被領取 | 無法重複領取；檢查系統狀態 |
| `ITEM_STATUS_INVALID` | 409 | 項目狀態不允許此操作 | 確認項目目前狀態，後續操作須符合狀態機 |
| `CARRIER_NOT_FOUND` | 404 | 指定的承運商 ID 不存在 | 確認承運商 ID 或使用預設值 |
| `DEPARTMENT_NOT_FOUND` | 404 | 部門 ID 不存在 | 確認部門已建立 |
| `OCR_CONFIDENTIAL_DISABLED` | 422 | 機密件禁止 AI OCR | 手動輸入欄位或改變機密件設定 |
| `NOT_FOUND` | 404 | 資源不存在 | 檢查 ID 是否正確 |
| `FORBIDDEN` | 403 | 沒有權限執行此操作 | 檢查 API key 的 scopes 或用戶角色 |
| `INTERNAL_ERROR` | 500 | 伺服器內部錯誤 | 稍後重試；持續失敗請聯絡技術支援 |

## 7. 最佳實踐

1. **API key 管理**
   - API key 絕不應存放在前端程式碼或版本控制中
   - 使用環境變數或密鑰管理系統存放
   - 定期輪換過期的 key

2. **錯誤處理**
   - 實作指數退避重試機制（尤其對 5xx 和 429 錯誤）
   - 記錄詳細的錯誤日誌以供偵錯
   - 向用戶展示友善的錯誤訊息

3. **Webhook 安全**
   - 必須驗證每個 webhook 的簽章
   - 在 5 分鐘內拒絕逾期的請求（防重放）
   - 使用 HTTPS 接收 webhook（不接受 HTTP）

4. **分頁與效能**
   - 大量查詢時使用分頁，預設每頁 50 筆
   - 充分利用篩選條件 (status、date_from/to 等) 減少數據傳輸

5. **事件幂等性**
   - Webhook 可能因網路問題重複遞送
   - 實作幂等性邏輯，重複事件不應產生重複效果（如用 `event.id` 去重）

## 8. 測試環境

開發測試可使用 Open Mail Room 的 Docker 示範環境：

```bash
docker-compose up -d
# 存取本地 API：http://localhost:8000/api/docs
```

管理後台可產生測試 API key（已啟用所有 scopes）。

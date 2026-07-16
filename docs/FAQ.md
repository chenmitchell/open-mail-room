# 自架常見問題 (FAQ)

本文件回答開源自架 Open Mail Room 時的常見問題與故障排除。

## 安全與密鑰管理

### Q: 金鑰遺失會怎樣？能恢復嗎？

**A:** Open Mail Room 使用以下金鑰，各有不同後果：

| 金鑰類型 | 遺失後果 | 能否恢復 | 建議 |
|---------|--------|--------|------|
| **Database 加密金鑰** (`ENCRYPTION_KEY` env var) | ⚠️ 致命：所有加密欄位（API keys、webhook secrets、簽名檔案）無法解密 | ❌ 不能 | **最關鍵**，務必備份。見 §2 |
| **Session JWT 金鑰** | 所有既有 session 失效，使用者被迫重新登入 | ✓ 無害 | 轉換鑰時自動處理 |
| **CSRF 金鑰** | 既有 CSRF token 失效，前端需重新取得 | ✓ 無害 | 保存重啟自動旋轉 |
| **API Key (第三方)** | 該 API key 無效，所有依賴它的呼叫失敗 | ✓ 可重新產生 | Admin UI 撤銷舊 key，產生新 key |
| **Webhook Secret** | 訂閱方無法驗證簽章，webhook 被拒 | ✓ 可重新產生 | Admin UI 編輯 webhook，手動更新訂閱方配置 |

**結論**：**Database 加密金鑰是唯一無法恢復的**，遺失即代表資料永久喪失。必須妥善保管。

### Q: 應該如何備份加密金鑰？

**A:** 建議的多層備份策略：

#### 層級 1: 在線存放（開發/測試環境）

```bash
# 儲存於 Docker .env 檔案
ENCRYPTION_KEY=your-base64-encoded-32-byte-key
```

**風險**：`.env` 不應簽入版本控制，應用 `.gitignore`

```gitignore
.env
.env.local
*.key
```

#### 層級 2: 環境變數管理（正式環境）

使用密鑰管理服務存放敏感配置：

**AWS Secrets Manager**：
```python
import boto3

def get_encryption_key():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId='openmailroom/encryption-key')
    return response['SecretString']
```

**HashiCorp Vault**：
```bash
vault kv get secret/openmailroom/encryption-key
```

**Azure Key Vault**：
```bash
az keyvault secret show --name encryption-key --vault-name openmailroom
```

#### 層級 3: 離線備份（物理保護）

針對最重要的 `ENCRYPTION_KEY`：

1. **產生備份複本**
   ```bash
   # 安全匯出金鑰（勿存在伺服器上）
   openssl rand -base64 32 > encryption_key_backup.txt
   ```

2. **加密備份** (AES-256)
   ```bash
   openssl enc -aes-256-cbc -salt -in encryption_key_backup.txt \
     -out encryption_key_backup.txt.enc -k "備份密碼"
   ```

3. **多地點存放**
   - 複本 1: 密鑰管理系統 (AWS/Vault)
   - 複本 2: 公司保險箱/物理金庫
   - 複本 3: 信任的 DBA 離線存放

4. **存取控制**
   - 限制知道備份位置的人員 (≤ 3 人)
   - 定期稽核存取紀錄
   - 離職時立即吊銷存取權

**重要**：永遠不要存多個明文副本，也不要存於共享雲端 (Google Drive/Dropbox) 無密碼共享。

### Q: API key 被攻擊者取得怎麼辦？

**A:** 立即應變步驟：

1. **撤銷 key**
   - Admin UI → API 密鑰管理 → 刪除該 key
   - 或 API: `DELETE /admin/api-keys/{id}`

2. **檢查稽核日誌**
   ```sql
   SELECT * FROM audit_logs 
   WHERE actor_type = 'api_key' 
     AND actor_id = '<compromised_key_id>'
   ORDER BY created_at DESC;
   ```

3. **檢查是否濫用**
   - 查看該 key 最後 24 小時的請求
   - 異常的 IP、endpoint、時間戳
   - 檢查是否有大量 `/ocr/jobs` 呼叫 (可能被用來濫用 AI 配額)

4. **重新簽發**
   - 通知依賴該 key 的第三方應用
   - Admin UI 產生新 key，發送至信任通道 (加密信件/Slack/Teams)
   - 給第三方 24 小時轉換期

5. **加強防線**
   - 檢查 Database 加密金鑰是否也洩漏
   - 考慮啟用 API key 的 IP 白名單
   - 增加 webhook 簽章驗證的嚴格度

### Q: 資料庫備份時應該備份哪些？

**A:** 完整備份需包含：

1. **PostgreSQL Database**
   ```bash
   pg_dump -U openmailroom --format=custom -f backup.sql.gz \
     openmailroom
   ```
   - 包含所有表格、索引、關聯
   - **加密欄位仍須 ENCRYPTION_KEY 才能解密** (備份本身是加密的)

2. **File Storage** (照片、簽名檔案)
   ```bash
   # 若用 Docker volume
   docker run --rm -v openmailroom_attachments:/data \
     -v backup_dir:/backup \
     alpine tar czf /backup/attachments.tar.gz -C /data .
   
   # 若用 S3
   aws s3 sync s3://openmailroom-attachments ./backup/attachments
   ```

3. **設定檔**
   ```bash
   # 複製 config/ 目錄
   cp -r config/ backup/config/
   
   # 複製 .env (含敏感配置)
   cp .env backup/.env.encrypted
   gpg --encrypt backup/.env.encrypted
   ```

4. **不需備份**
   - Docker images (可從 registry 重新拉取)
   - 暫時檔案 (`/tmp` 目錄)
   - 日誌檔案 (容量大，監控系統應有備份)

### Q: 金鑰輪換流程是什麼？

**A:** 定期輪換 (建議每季度):

#### Database 加密金鑰輪換

**複雜度**: 高 ⚠️ (涉及資料重加密)

```python
# 1. 備份現有資料
pg_dump -Fc openmailroom > backup_before_rotation.sql.gz

# 2. 生成新金鑰
export NEW_ENCRYPTION_KEY=$(openssl rand -base64 32)

# 3. 執行資料遷移 (假設使用 Alembic)
#    需編寫自訂遷移腳本，逐行讀舊金鑰解密 → 新金鑰加密
#    参考: alembic/versions/xxxx_rotate_encryption_key.py

# 4. 更新環境變數
export ENCRYPTION_KEY=$NEW_ENCRYPTION_KEY

# 5. 重啟應用
docker-compose restart backend

# 6. 驗證
# 檢查 Admin Dashboard 是否仍能正常存取加密欄位
curl -H "Authorization: Bearer $API_KEY" \
  https://mailroom.example.com/api/v1/admin/ai-providers
# 應該返回正常的 AI provider 清單，API keys 仍被遮罩
```

**建議**：此流程複雜，建議由有 DB 經驗的團隊執行，且需維護窗口 (系統短暫不可用)。

#### Session/CSRF 金鑰輪換

**複雜度**: 低 (無狀態，自動處理)

```bash
# 更新環境變數
export SESSION_SECRET=$(openssl rand -base64 32)
export CSRF_SECRET=$(openssl rand -base64 32)

# 重啟應用
docker-compose restart backend

# 既有 session 失效，使用者自動重新登入
```

## 備份與還原

### Q: 如何備份與還原整個系統？

**A:** 完整備份/還原步驟：

#### 備份

```bash
#!/bin/bash
# backup.sh - 完整系統備份

BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. 資料庫備份
pg_dump -U openmailroom -h localhost openmailroom | \
  gzip > "$BACKUP_DIR/database.sql.gz"
echo "✓ Database backup"

# 2. 檔案備份
docker run --rm -v openmailroom_attachments:/data \
  -v "$(pwd)/$BACKUP_DIR:/backup" \
  alpine tar czf /backup/attachments.tar.gz -C /data .
echo "✓ Attachments backup"

# 3. 設定備份
cp -r config/ "$BACKUP_DIR/config/"
echo "✓ Configuration backup"

# 4. Docker Compose 備份
cp docker-compose.yml "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/.env.encrypted"
# 加密 .env (含敏感資料)
gpg --symmetric --cipher-algo AES256 "$BACKUP_DIR/.env.encrypted"
rm "$BACKUP_DIR/.env.encrypted"  # 刪除未加密版本
echo "✓ Environment & compose backup"

# 5. 壓縮備份
tar czf "backup_complete_$(date +%Y%m%d_%H%M%S).tar.gz" "$BACKUP_DIR"
echo "✓ Complete backup created"

# 6. 上傳至外部儲存 (可選)
# aws s3 cp "backup_complete_*.tar.gz" s3://openmailroom-backups/
```

**執行備份**：
```bash
chmod +x backup.sh
# 立即執行
./backup.sh

# 或排程每天執行
(crontab -l 2>/dev/null; echo "2 3 * * * cd /opt/openmailroom && ./backup.sh") | crontab -
# 每天 03:02 執行備份
```

#### 還原

```bash
#!/bin/bash
# restore.sh - 完整系統還原

BACKUP_FILE=$1  # 傳入備份檔案名稱

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 backup_complete_YYYYMMDD_HHMMSS.tar.gz"
  exit 1
fi

# 1. 解壓備份
mkdir -p restore_temp
tar xzf "$BACKUP_FILE" -C restore_temp/
BACKUP_DIR=$(ls -d restore_temp/backup_* | head -1)

# 2. 停止應用
docker-compose down
echo "✓ Application stopped"

# 3. 恢復資料庫
# 警告：此操作將覆蓋現有資料庫
read -p "This will overwrite the database. Continue? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  gunzip < "$BACKUP_DIR/database.sql.gz" | \
    psql -U openmailroom -h localhost openmailroom
  echo "✓ Database restored"
fi

# 4. 恢復檔案
docker run --rm -v openmailroom_attachments:/data \
  -v "$(pwd)/$BACKUP_DIR:/backup" \
  alpine tar xzf /backup/attachments.tar.gz -C /data
echo "✓ Attachments restored"

# 5. 恢復設定
cp -r "$BACKUP_DIR/config" ./
echo "✓ Configuration restored"

# 6. 恢復環境變數
gpg --decrypt "$BACKUP_DIR/.env.encrypted.gpg" > .env
chmod 600 .env
echo "✓ Environment restored"

# 7. 啟動應用
docker-compose up -d
echo "✓ Application started"

# 8. 驗證
sleep 5
curl http://localhost:8000/healthz
echo "✓ Restore complete"

# 清理
rm -rf restore_temp/
```

**執行還原**：
```bash
chmod +x restore.sh
./restore.sh backup_complete_20260709_030200.tar.gz
```

### Q: 備份應該多久執行一次？

**A:** 根據資料重要性：

| 環境 | 備份頻率 | 保留期 | 建議儲存位置 |
|------|--------|--------|------------|
| 開發 | 每週 1 次 | 4 週 | 本地磁碟 |
| 測試 | 每日 1 次 | 2 週 | 本地 + 異地 1 份 |
| 正式 | 每日 2 次 (凌晨+午夜) | 90 天 | 多地 (本地+AWS S3+實體) |

**RPO/RTO 目標**：
- RPO (Recovery Point Objective): 最多丟失 1 小時的資料 → 備份間隔 ≤ 1 小時
- RTO (Recovery Time Objective): 24 小時內恢復 → 測試還原程序每月 1 次

### Q: 資料庫損毀無法啟動怎麼辦？

**A:** 緊急恢復程序：

```bash
# 1. 停止應用
docker-compose down

# 2. 檢查 PostgreSQL 健康狀態
docker-compose up -d db
docker exec openmailroom_db pg_isready

# 3. 若 DB 無法啟動，查看日誌
docker logs openmailroom_db | tail -50

# 4. 若磁碟滿或檔案損毀，嘗試恢復模式啟動
# 在 docker-compose.yml 修改 postgres 環境變數
# environment:
#   POSTGRES_INITDB_ARGS: "-c wal_level=minimal"

# 5. 若無法修復，還原備份
./restore.sh latest_backup.tar.gz

# 6. 驗證恢復
docker exec openmailroom_backend python -c \
  "from app.db import SessionLocal; db = SessionLocal(); print(db.execute('SELECT COUNT(*) FROM mail_items').scalar())"
```

## 功能與配置

### Q: LINE 通知有免費額度嗎？

**A:** 是的。自 2025 年 4 月起，LINE Notify 已停用，改用 LINE Official Account (OA) + Messaging API。

**免費額度** (2026 年台灣資費)：
- 輕用量方案: **0 元/月** (免費)
- 免費推播額度: **200 則/月** (Push 計費，Reply 不計費)

**計費方式**：
- 超過 200 則後: $0.015 USD/則 (約台幣 0.5 元)
- 每月回覆訊息: 不計費 (無限)

**成本估算**：
- 小公司 (50 件/天): ~1500 則/月 → 超量 1300 則 × $0.015 = **$19.5/月**
- 中公司 (200 件/天): ~6000 則/月 → 超量 5800 則 × $0.015 = **$87/月**
- 大公司 (500+件/天): 明顯超出，建議升級計費方案

**建議**：
1. 小用量: 使用免費 200 則，超額用 Telegram/Email
2. 中用量: 升級至標準方案 ($400-500/月)
3. 大用量: 企業方案 (客製化)

**無法省成本時**：考慮 Telegram (完全免費，額度無限) 或 Email 作主要通道。

### Q: HTTPS 與內網自簽憑證如何設定？

**A:** Open Mail Room 前端需要 HTTPS (特別是 PWA、Web Push、相機存取)。

#### 正式環境 (Let's Encrypt 自動化)

```bash
# 使用 Caddy 反向代理，自動獲取 Let's Encrypt 憑證
# docker-compose.yml 新增

caddy:
  image: caddy:latest
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./Caddyfile:/etc/caddy/Caddyfile
    - caddy_data:/data
    - caddy_config:/config
  networks:
    - openmailroom

# Caddyfile
mailroom.example.com {
  reverse_proxy backend:8000
}
```

#### 內網環境 (自簽憑證)

```bash
# 1. 產生自簽 CA 憑證
openssl genrsa -out ca-key.pem 2048
openssl req -new -x509 -days 3650 -key ca-key.pem -out ca.pem \
  -subj "/CN=Open Mail Room-CA"

# 2. 產生伺服器憑證請求
openssl genrsa -out server-key.pem 2048
openssl req -new -key server-key.pem -out server.csr \
  -subj "/CN=mailroom.internal"

# 3. 簽署憑證 (有效期 1 年)
openssl x509 -req -days 365 -in server.csr \
  -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out server.pem

# 4. 信任自簽 CA (客戶端)
# macOS
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.pem

# Linux (Ubuntu/Debian)
sudo cp ca.pem /usr/local/share/ca-certificates/openmailroom-ca.crt
sudo update-ca-certificates

# Windows
certutil -addstore -f "ROOT" ca.pem
```

**Docker 設定**：
```yaml
services:
  frontend:
    environment:
      VITE_API_URL: "https://mailroom.internal/api/v1"
    # 自簽憑證禁用驗證只用於開發
      NODE_TLS_REJECT_UNAUTHORIZED: "0"  # ⚠️ 危險！生產禁用
```

**隱患**：
- 自簽憑證無法 Web Push (PWA 通知會失敗)
- 瀏覽器會警告 "不安全的連線"
- 建議內網仍申請正式 SSL (或用企業 CA)

### Q: 離線使用 (地下室、無網路) 如何設定？

**A:** Open Mail Room 設計考慮了離線場景 (收發室常在地下室)。

#### 離線支援功能

1. **PWA Offline Queue** (已實作)
   - 無網路時拍照、表單存於 IndexedDB
   - 恢復連線自動補送
   - 確保「拍照但網路掉線」不會遺失資料

2. **本地 Ollama OCR** (推薦)
   - 照片完全本地處理，不上傳
   - 模型下載至本地後無需網路
   - 速度較雲端 AI 慢 (20-30 秒/張)

3. **條碼掃描** (總是可用)
   - ZXing 客戶端掃描，無網路依賴
   - 能取得 90% 常見單號

#### 設定步驟

1. **容器內安裝 Ollama**
   ```dockerfile
   # Dockerfile.ollama
   FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04
   RUN curl https://ollama.ai/install.sh | sh
   RUN ollama pull qwen:7b-vision-q5_K_M
   CMD ["ollama", "serve"]
   ```

2. **Docker Compose 設定**
   ```yaml
   ollama:
     build:
       context: .
       dockerfile: Dockerfile.ollama
     ports:
       - "11434:11434"
     volumes:
       - ollama_models:/root/.ollama
     environment:
       OLLAMA_NUM_PARALLEL: 1  # 單 GPU 限制並行
   
   backend:
     environment:
       # 設定 Ollama 為預設 OCR 提供商
       AI_PROVIDER_PRIMARY: "ollama"
       AI_PROVIDER_BASE_URL: "http://ollama:11434/v1"
   ```

3. **Admin UI 設定**
   - AI 提供商 → 新增 → Provider: OpenAI (Ollama 相容)
   - Base URL: `http://ollama:11434/v1`
   - Model: `qwen:7b-vision-q5_K_M`
   - Priority: 10 (首選)

#### 完全離線測試

```bash
# 1. 斷開網路
sudo ifconfig eth0 down  # Linux
# 或 System Preferences → Network (macOS)

# 2. 確認 backend ↔ ollama 連通 (內網)
docker exec openmailroom_backend curl http://ollama:11434/api/tags

# 3. 測試拍照 + OCR
# 前端上傳照片 → 應成功處理

# 4. 恢復網路
sudo ifconfig eth0 up
```

#### 離線佇列驗證

```javascript
// 前端 DevTools Console
// 檢查 IndexedDB 離線佇列
const db = await openDB('openmailroom-offline');
const queue = await db.getAll('upload_queue');
console.log('Pending uploads:', queue);
```

**限制**：
- 員工名錄不更新 (若需新增員工須有網路)
- 無法同步他人最新資訊
- 建議每天連線一次同步

## 部署與維運

### Q: Docker 容器記憶體用量很大，如何優化？

**A:** Open Mail Room 各元件的典型記憶體佔用：

| 服務 | 預設限制 | 實際用量 | 優化建議 |
|------|--------|--------|--------|
| PostgreSQL | 512MB | 300-400MB | 生產環境升至 1GB+ |
| Backend (FastAPI) | 512MB | 200-300MB | 增加 worker 數量但降低每個的限制 |
| Frontend (Node.js) | 256MB | 100-150MB | 構建時啟用 terser 壓縮 |
| Redis (若用) | 256MB | 50-100MB | 設定 `maxmemory-policy=allkeys-lru` |

**優化措施**：

```yaml
# docker-compose.yml
backend:
  deploy:
    resources:
      limits:
        memory: 1G  # 升級
        cpus: "1"
      reservations:
        memory: 512M
        cpus: "0.5"

db:
  deploy:
    resources:
      limits:
        memory: 2G  # PostgreSQL 分配更多
      reservations:
        memory: 1G

# PostgreSQL 調參 (docker-compose 環境變數)
db:
  environment:
    POSTGRES_INIT_ARGS: "-c shared_buffers=256MB -c effective_cache_size=1GB -c work_mem=64MB"
```

**監控記憶體**：
```bash
docker stats --no-stream
# 或每 5 秒更新
watch -n 5 docker stats
```

### Q: 如何設定個資法保存期限？

**A:** Open Mail Room 提供自動資料銷毀機制，符合台灣個資法第 3 條 (告知義務) 與第 11 條 (保存期限)。

#### 法律背景

**台灣個資法**：
- 蒐集目的達成時應「儘速」銷毀
- 無其他法律保留義務時，通常 1-3 年內銷毀
- 特定行業可能有更長保留期 (金融 5 年、醫療 7 年等)

**Open Mail Room 預設**：
```yaml
# config/branding.yaml
retention_years: 5  # 保留 5 年後自動匿名化
```

#### 設定步驟

1. **確認法務要求**
   - 公司適用的法律 (台灣個資法、GDPR 等)
   - 是否有特殊保留需求 (稅務、健保等)

2. **設定保留期**
   ```yaml
   retention_years: 3  # 或 5、7 依需求
   ```

3. **自動銷毀排程**
   ```python
   # backend/app/tasks/data_retention.py (系統自動執行)
   async def anonymize_old_records():
       """每天執行一次，銷毀超過 retention_years 的記錄"""
       cutoff_date = datetime.now(timezone.utc) - timedelta(days=365*retention_years)
       
       # 匿名化郵件項目
       await session.execute(
           update(MailItem)
           .where(MailItem.received_at < cutoff_date)
           .values(
               sender_name=None,
               sender_org=None,
               sender_phone=None,
               recipient_name_raw="[已匿名化]"
           )
       )
       
       # 刪除附件檔案
       attachments = await session.execute(
           select(Attachment)
           .where(Attachment.created_at < cutoff_date)
       )
       for att in attachments.scalars():
           os.unlink(att.file_path)
       
       await session.commit()
   ```

4. **稽核與報表**
   - Admin Dashboard 顯示「將於 X 天後銷毀的記錄」
   - 匿名化事件記錄於 audit_logs
   - 法務可查詢銷毀清冊

#### 隱私通知

系統自動在登入頁、設定頁展示隱私聲明：

```
本系統依台灣個人資料保護法蒐集、使用郵件資訊。
蒐集目的：人事部門郵件管理與快遞追蹤。
保留期限：自收件日起 5 年，期滿自動刪除個人識別資訊。
你的權利：有權查詢、請求複製、補正、刪除個人資料。
聯絡我們：privacy@company.com
```

### Q: 無法連接到 AI 提供商 (Timeout)，如何診斷？

**A:** 分步驟診斷：

#### 1. 檢查網路連通性

```bash
# 從 backend 容器測試
docker exec openmailroom_backend curl -v https://api.openai.com/v1/models

# 若 Timeout，檢查防火牆/代理設定
docker exec openmailroom_backend curl -x http://proxy.example.com:8080 \
  https://api.openai.com/v1/models
```

#### 2. 檢查 API Key 有效性

```bash
# 手動測試 API key
curl -H "Authorization: Bearer sk-proj-xxxxx" \
  https://api.openai.com/v1/models | head -20
```

#### 3. 查看後端日誌

```bash
docker logs openmailroom_backend | grep -i "ocr\|provider\|timeout"

# 或查詢資料庫
SELECT * FROM audit_logs 
WHERE action LIKE '%ocr%' 
ORDER BY created_at DESC LIMIT 10;
```

#### 4. 檢查 Admin Dashboard

- AI 提供商 → 檢查 `last_success_at` 與 `failure_count`
- 若 failure_count > 3，系統已自動降優先度
- 若失敗達 20 次，自動停用並通知 admin

#### 5. 測試 Webhook

```bash
# Admin UI → AI 提供商 → 測試
# 或 API
curl -X POST https://mailroom.example.com/api/v1/admin/ai-providers/{id}/test \
  -H "Authorization: Bearer sk_live_xxxxx" \
  -H "Content-Type: application/json"

# 回應應該是成功或清楚的錯誤訊息
# {"data": {"success": true}, "error": null}
```

#### 6. 常見原因與解決

| 症狀 | 原因 | 解決 |
|------|------|------|
| Connection timeout | 網路/防火牆阻擋 | 檢查出站連線規則；若公司代理須設定代理 URL |
| 401 Unauthorized | API key 無效或過期 | 驗證 key；重新產生 |
| 429 Too Many Requests | 超過速率限制 | 檢查月預算；降低請求頻率 |
| 503 Service Unavailable | AI 服務中斷 | 等待或切換備選提供商 |
| SSL Certificate Error | 自簽憑證或時間不同步 | 更新系統時間；或信任自簽 CA |

### Q: 容器經常 OOMKill，如何解決？

**A:** Out of Memory 問題通常由以下原因造成：

#### 原因診斷

```bash
# 檢查 OOMKill 事件
docker inspect openmailroom_backend | grep -A 5 "OOMKilled"

# 或查看系統日誌
dmesg | grep -i "killed process"
```

#### 解決方案

1. **增加容器記憶體限制**
   ```yaml
   backend:
     deploy:
       resources:
         limits:
           memory: 2G  # 從 512MB 升至 2GB
   ```

2. **優化應用程式**
   ```python
   # backend/main.py
   # 減少並行 worker，每個用較少記憶體
   uvicorn.run(
       app,
       workers=2,  # 從 4 改為 2
       loop="uvloop"  # 使用 uvloop 省記憶體
   )
   ```

3. **啟用記憶體交換 (swap)**
   ```bash
   # 系統層級設定 (Docker host)
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   
   # 持久化 (添加到 /etc/fstab)
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

4. **監控與警告**
   ```bash
   # 設定記憶體使用率警告 (80%)
   # 可結合 Prometheus + Alertmanager
   ```

#### 防止未來發生

- 定期監控 `docker stats`
- 設定資源預約和限制
- 實作自動 scaling (若使用 Kubernetes)

---

## 技術支援

若問題無法解決，請提供：
1. **Docker logs**: `docker-compose logs --tail=100 > logs.txt`
2. **系統資訊**: `docker version`, `docker ps`
3. **browser 主控台**錯誤訊息 (F12 → Console)
4. **複現步驟**：精確的操作步驟

聯絡方式：
- GitHub Issues: https://github.com/openmailroom/openmailroom/issues
- 討論區: GitHub Discussions
- 郵件: support@openmailroom.local

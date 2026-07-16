# Open Mail Room 安裝指南

## 目錄
1. [系統需求](#系統需求)
2. [一鍵部署](#一鍵部署)
3. [密鑰備份（重要）](#密鑰備份重要)
4. [部署選項](#部署選項)
5. [自簽憑證（內網）](#自簽憑證內網)
6. [升級](#升級)
7. [還原](#還原)
8. [故障排除](#故障排除)

---

## 系統需求

### 硬體
- **CPU**: 2+ cores
- **RAM**: 4GB (8GB 建議用於多用戶)
- **磁碟**: 50GB+ (依照片保存期限調整)

### 軟體
- **Docker**: ≥ 24.0
- **Docker Compose**: ≥ 2.20
- **curl**: 用於健康檢查
- **openssl**: 用於金鑰生成

### 網路
- **公開部署**: 需要域名且能自動申請 Let's Encrypt 憑證
- **內網部署**: 可使用自簽憑證或直接 HTTP (不建議)

### 作業系統
支援: Linux (建議), macOS (開發/測試), Windows with WSL2

---

## 一鍵部署

### 步驟 1: 下載 Open Mail Room

```bash
git clone https://github.com/YOUR-USERNAME/open-mail-room.git
cd open-mail-room
```

### 步驟 2: 執行部署腳本

#### 公開部署（自動 HTTPS）

```bash
cd deploy
chmod +x deploy.sh
DOMAIN=mailroom.example.com ./deploy.sh
```

腳本會自動：
1. 產生隨機加密金鑰並儲存到 `.env`
2. 提醒備份 `ENCRYPTION_KEY`（**極為重要**）
3. 拉取/構建 Docker 映像
4. 啟動全部服務
5. 檢驗健康狀態

#### 內網部署（自簽憑證）

```bash
cd deploy
chmod +x deploy.sh selfsigned.sh

# 產生自簽憑證
./selfsigned.sh localhost

# 更新 docker-compose 使用自簽設定
# （見「自簽憑證」章節）

# 執行部署
./deploy.sh
```

### 步驟 3: 首次登入

1. 開啟瀏覽器：
   - 公開: `https://mailroom.example.com`
   - 內網: `https://localhost` (接受自簽憑證警告)

2. 用 `.env` 中的 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 登入

3. **立即變更管理員密碼**（Admin > Settings > Change Password）

---

## 密鑰備份（重要）

### ⚠️ 警告

**ENCRYPTION_KEY 遺失 = 無法永久復原所有照片和個人資料欄位**

此金鑰用於加密：
- 員工信箱、電話
- 收件人住址、電話
- 所有上傳的照片和簽名檔
- 寄件人聯繫資訊
- 通知設定綁定

### 備份程序

#### 部署後立即執行

部署完成時，`.env` 檔案會印出 ENCRYPTION_KEY。**立即複製到安全位置**：

```bash
# 顯示金鑰
grep ENCRYPTION_KEY .env

# 推薦做法：
# 1. 儲存到密碼管理器（1Password, Bitwarden, KeePass）
# 2. 列印紙本副本，放入保險箱
# 3. 建立加密備份副本到單獨的雲端儲存空間（不要和資料庫在同一地點）

# 不推薦：貼在便簽紙上、明文存到郵件、存到未加密的雲端
```

#### 定期驗證

每月檢查一次備份副本是否可讀取（試著從別臺電腦存取）。

### 金鑰輪替（高級）

若懷疑金鑰外洩，見 `docs/SECURITY.md` 的「金鑰輪替」章節（v1.5+）。

---

## 部署選項

### 選項 A: 自動 HTTPS（公開部署）

**適合**: 生產環境、公司網站

```bash
DOMAIN=mailroom.example.com ./deploy.sh
```

**要求**:
- 域名解析到主機 IP
- 防火牆開放 80 (HTTP 重導) 和 443 (HTTPS)
- 可自動申請 Let's Encrypt

**優點**:
- 瀏覽器信任，無警告
- 自動續期 (Caddy 內建)
- 支援 mobile PWA 推播

### 選項 B: 自簽憑證（內網/測試）

**適合**: 內部網路、測試環境

```bash
cd deploy
./selfsigned.sh myhost.local
# 編輯 docker-compose.yml，改用 Caddyfile.selfsigned
./deploy.sh
```

**要求**:
- 無需域名或網際網路
- 客戶端需接受自簽憑證

**優點**:
- 完全離線
- 無續期煩惱

**缺點**:
- 瀏覽器每次警告
- iOS PWA 不支援

### 選項 C: 開發 HTTP

**僅限開發**，不適合生產:

```bash
# 編輯 Caddyfile，移除 TLS 設定
# 編輯 docker-compose.yml，只開放 :80
```

---

## 自簽憑證（內網）

### 生成憑證

```bash
cd deploy
chmod +x selfsigned.sh
./selfsigned.sh myhost.local 365
```

輸出:
- `ssl/cert.pem` - 公鑰憑證
- `ssl/private.key` - 私鑰（保密！）
- `Caddyfile.selfsigned` - Caddy 設定

### 部署

1. 複製憑證到 docker compose volume:
```bash
mkdir -p ssl-volume
cp ssl/{cert.pem,private.key} ssl-volume/
```

2. 編輯 `docker-compose.yml`:
```yaml
caddy:
  volumes:
    - ./Caddyfile.selfsigned:/etc/caddy/Caddyfile:ro
    - ./ssl-volume:/etc/caddy/certs:ro
```

3. 啟動:
```bash
./deploy.sh
```

### 信任憑證（選擇性）

#### Linux (Ubuntu/Debian)
```bash
sudo cp ssl/cert.pem /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

#### macOS
```bash
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ssl/cert.pem
```

#### Windows
```powershell
Import-Certificate -FilePath .\ssl\cert.pem -CertStoreLocation Cert:\CurrentUser\Root
```

#### 不信任情況下測試
```bash
curl -k https://myhost.local/healthz
```

---

## 升級

### 備份前置

```bash
# 停止服務
docker compose down

# 備份資料庫與設定
cp -r data data.backup.$(date +%Y%m%d)
cp .env .env.backup
```

### 升級步驟

```bash
# 拉取新版本
git pull origin main

# 檢視變更日誌
cat CHANGELOG.md

# 執行新版本的 deploy.sh
cd deploy
./deploy.sh
```

**Caddy 和 docker compose 會自動處理 migration**。

### 驗證升級

```bash
# 檢查服務狀態
docker compose ps

# 查看日誌
docker compose logs -f backend
```

---

## 還原

### 準備工作

確保你有：
1. 最近一份資料庫備份 (`data/openmailroom.db`)
2. 對應的 `ENCRYPTION_KEY` (若資料是加密的)
3. 對應版本的程式碼 (通常是升級前的 git commit)

### 還原步驟

```bash
# 1. 停止當前服務
docker compose down

# 2. 還原檔案
rm data/openmailroom.db
cp data.backup.YYYYMMDD/openmailroom.db data/

# 3. 還原環境設定（若改過）
cp .env.backup .env

# 4. 檢查金鑰
grep ENCRYPTION_KEY .env  # 確認仍是原始金鑰

# 5. 還原程式碼版本（選擇性）
git checkout <commit-hash>

# 6. 重新啟動
cd deploy && ./deploy.sh
```

### 演練備份還原

**重要**: 每季度演練一次完整還原，以確保備份確實可用。

```bash
# 在測試主機上：
1. 複製生產資料庫
2. 執行上述還原步驟
3. 驗證資料完整性
4. 測試關鍵功能
5. 記錄還原時間與結果
```

---

## 故障排除

### 啟動失敗：`Health check failed`

檢查服務日誌:
```bash
docker compose logs backend
docker compose logs caddy
```

常見原因:
- **`ENCRYPTION_KEY` 缺少或格式錯誤** → 檢查 `.env`
- **連接埠已被佔用** → `sudo lsof -i :80,443,8000`
- **磁碟空間不足** → `df -h`
- **Docker daemon 未運行** → `docker ps`

### 無法存取 Web UI

1. 檢查 DNS:
```bash
nslookup mailroom.example.com  # 應返回主機 IP
```

2. 檢查防火牆:
```bash
# Linux
sudo ufw status
sudo ufw allow 80,443/tcp

# macOS
sudo pfctl -s rules | grep 443
```

3. 檢查 Caddy 設定:
```bash
docker compose logs caddy | grep -i error
```

### 登入失敗

**症狀**: "Invalid credentials" (雖然密碼正確)

原因及解決:
1. `.env` 中的 `ADMIN_PASSWORD` 與登入密碼不符
   - 重設: 見「首次登入」步驟 3
2. Session cookie 過期
   - 清除瀏覽器 cookie，重新登入
3. `SECRET_KEY` 變更導致 session 失效
   - 所有使用者需重新登入

### 高磁碟使用率

檢查容量:
```bash
du -sh data/

# 分析照片大小
find data -name "*.jpg" -o -name "*.png" | xargs du -ch | tail -1
```

清理:
1. 檢視 `config/branding.yaml` 中的 `retention_years` 設定
2. 執行手動清理（v1.1+）:
   ```bash
   docker compose exec backend \
     python -m app.tasks.cleanup --dry-run
   ```

### 記憶體使用率過高

調整 docker-compose 資源限制:
```yaml
backend:
  deploy:
    resources:
      limits:
        memory: 2G
      reservations:
        memory: 1G
```

重啟: `docker compose up -d`

### 照片 OCR 失敗

1. 檢查 AI provider 設定:
```bash
docker compose logs backend | grep -i ocr
```

2. 檢查 API key:
```bash
grep -E "OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE" .env
```

3. 檢查佇列狀態:
```bash
# 見 docs/API.md 中的「佇列管理」
curl https://mailroom.example.com/api/admin/tasks
```

### 通知不送達

1. 檢查通知通道設定:
   - Admin > Notification Channels
   - 驗證 API token 是否有效

2. 檢查日誌:
```bash
docker compose logs backend | grep -i notify
```

3. 測試通知:
```bash
# Admin UI 中的 Test 按鈕，或：
curl -X POST https://mailroom.example.com/api/admin/notify/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "email", "recipient": "test@example.com"}'
```

---

## 進階話題

### PostgreSQL 部署

預設使用 SQLite (單機)。用 PostgreSQL 以支援多主機：

```bash
# 啟動 PostgreSQL profile
docker compose --profile postgres up -d

# 更新 .env
DATABASE_URL=postgresql://openmailroom:password@postgres:5432/openmailroom
```

### S3 備份

設定 AWS S3 自動備份（見 `config/backup.yaml`）。

### Prometheus 監控

收集指標:
```bash
curl https://mailroom.example.com/api/metrics
```

### 自訂品牌

編輯 `config/branding.yaml`，重啟 caddy:
```bash
docker compose restart caddy
```

---

## 獲得支援

- **文件**: https://github.com/YOUR-USERNAME/open-mail-room/tree/main/docs
- **Issue 回報**: https://github.com/YOUR-USERNAME/open-mail-room/issues
- **討論**: https://github.com/YOUR-USERNAME/open-mail-room/discussions
- **郵件**: contact@example.com

---

**最後更新**: 2024-12-20  
**版本**: Open Mail Room v1.0.0

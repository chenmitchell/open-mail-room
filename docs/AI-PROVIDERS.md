# AI OCR 提供商設定指南

本文件說明如何設定 Open Mail Room 的 AI OCR 功能。系統採用「條碼優先，AI 補位」策略：前端先用 ZXing 掃條碼提取單號（免費、快速），AI 則負責提取寄件人、收件人、承運商判斷等條碼無法取得的欄位。

## 1. 核心原則

### 為何需要 AI OCR？

條碼掃描 (ZXing) 無法取得以下資訊：
- 寄件人姓名與公司
- 寄件人電話
- 收件人細節（手寫欄位）
- 承運商判斷（從標籤視覺識別）
- 信封背面的寄件人資訊

**AI 的角色**：補完條碼拿不到的欄位，同時驗證條碼結果。

### API Key 安全

- **絕不下發前端**：API key 加密存放於資料庫，後端持有
- **前端只看遮罩**：UI 顯示 `sk-***abc` (前 3 字 + 末 3 字)
- **SSRF 防護**：`base_url` 經過驗證，不可指向內網服務（除非顯式開啟 `allow_private_network: true`）

### 人工確認是最後防線

OCR 結果僅為「草稿」(draft)，不直接入庫。流程：
1. 使用者拍照上傳 → OCR 處理
2. 系統展示 OCR 結果預填欄位 + 員工候選
3. 使用者確認或修正 → 提交正式記錄

**信心度 < 70% 的欄位** 系統會標記警示，讓使用者仔細確認。

## 2. 支援的 AI 提供商

Open Mail Room 採用抽象層設計，支援多個 AI 提供商，可依需求選擇或組合。

### OpenAI (包含 OpenRouter 相容服務)

**支援的模型**（2026-07 推薦）：
- `gpt-4o-mini` (推薦) — 快速、成本低、準度高
- `gpt-4-turbo`
- 任何 OpenAI 相容的 API (如 OpenRouter、Groq、LiteLLM、Together)

**設定步驟**：

1. 取得 API key（[OpenAI Platform](https://platform.openai.com/api-keys)）
2. 進入 Open Mail Room 管理後台 → **AI 提供商** → **新增**
3. 填寫表單：

| 欄位 | 值 |
|------|-----|
| Provider | `OpenAI` |
| Base URL | (留空使用官方，或填自訂相容服務) |
| API Key | `sk-proj-xxxxx` |
| Model | `gpt-4o-mini` |
| Priority | `10` (數字小 = 優先度高) |
| Monthly Budget | `50` (US$) |
| Is Active | ✓ |
| Allow Private Network | (根據需要) |

4. 測試：保存後系統自動驗證 key 有效性

**成本估算** (2026-07)：
- Input: ~$0.15/M tokens
- Output: ~$0.60/M tokens
- 平均一張標籤: 1k～2k input + 500 output tokens ≈ $0.002
- **每千件約 US$2**

**其他相容服務**（填自訂 base_url）：

| 服務 | Base URL | 支援模型 |
|------|----------|--------|
| OpenRouter | `https://openrouter.ai/api/v1` | 100+ 模型自選 |
| Groq | `https://api.groq.com/openai/v1` | `mixtral-8x7b-32768` 等 |
| LiteLLM | `http://localhost:4000/v1` | (本地代理) |
| Azure OpenAI | `https://{resource}.openai.azure.com/v1` | 指定部署名稱 |

### Anthropic Claude

**支援的模型**（2026-07 推薦）：
- `claude-haiku-4-5` (推薦) — 輕量、成本低
- `claude-3.5-sonnet`
- `claude-opus`

**設定步驟**：

1. 取得 API key（[Anthropic Console](https://console.anthropic.com/api-keys)）
2. 管理後台 → **AI 提供商** → **新增**

| 欄位 | 值 |
|------|-----|
| Provider | `Anthropic` |
| Base URL | (自動) |
| API Key | `sk-ant-xxxxx` |
| Model | `claude-haiku-4-5` |
| Priority | `20` |
| Monthly Budget | `50` (US$) |

**成本估算** (2026-07)：
- haiku Input: ~$0.08/M tokens
- haiku Output: ~$0.24/M tokens
- 平均標籤 ≈ $0.0015
- **每千件約 US$1.5** (最便宜選項)

### Google Gemini

**支援的模型**（2026-07 推薦）：
- `gemini-2.0-flash` (推薦) — 快速、免費額度充裕
- `gemini-1.5-pro`
- `gemini-1.5-flash`

**設定步驟**：

1. 建立 Google Cloud 專案，啟用 Vertex AI API
2. 取得 API key ([Google Cloud Console](https://console.cloud.google.com/apis/credentials))
3. 管理後台 → **AI 提供商** → **新增**

| 欄位 | 值 |
|------|-----|
| Provider | `Google Gemini` |
| Base URL | (自動) |
| API Key | `AIza...` |
| Model | `gemini-2.0-flash` |
| Priority | `30` |
| Monthly Budget | `50` (US$) |

**成本估算** (2026-07)：
- Input: ~$0.075/M tokens (前 1M 免費)
- Output: ~$0.30/M tokens
- 平均標籤 ≈ $0.0015～0 (可能免費層涵蓋)

**注意**：免費額度限制，高量級部署建議切換計費方案。

### OpenRouter (聚合服務)

OpenRouter 整合 100+ 模型，支援多重 failover 與費率控制。

**優勢**：
- 單一 API key 存取多個模型
- 自動故障轉移 (一個模型掛掉自動用備選)
- 價格聚合與追蹤

**設定步驟**：

1. 註冊 [OpenRouter](https://openrouter.ai)，取得 API key
2. 管理後台 → **AI 提供商** → **新增**

| 欄位 | 值 |
|------|-----|
| Provider | `OpenAI` (因 OpenRouter 相容) |
| Base URL | `https://openrouter.ai/api/v1` |
| API Key | `sk-or-v1-xxxxx` |
| Model | `openai/gpt-4o-mini` (或任選) |
| Priority | `10` |
| Monthly Budget | `50` (US$) |

**推薦模型組合**（按成本）：
- `mistralai/mistral-7b-instruct:free` (免費)
- `meta-llama/llama-2-70b-chat:free` (免費)
- `openai/gpt-4o-mini` (便宜)

### 本地 Ollama (離線/隱私)

適合對資料隱私敏感、不願上傳照片至雲端的組織。

**優勢**：
- 照片不離開內網
- 完全免費（只需機器資源）
- 符合「無雲」或「中國大陸」等法規限制

**缺點**：
- 準度不如雲端大模型（Qwen-VL 約 60-70% 準度 vs. 85%+）
- 需自行維護伺服器資源
- 初次啟動慢（模型下載 + 加載）

**設定步驟**：

1. 安裝 Ollama ([ollama.ai](https://ollama.ai))
   ```bash
   # 下載並執行 Ollama
   ollama run qwen:7b-vision-q5_K_M  # 約 5GB，支援圖像
   # 或
   ollama run llava:latest             # 另一選項
   ```

2. 確保 Ollama 服務執行於 `http://localhost:11434` (預設)

3. 管理後台 → **AI 提供商** → **新增**

| 欄位 | 值 |
|------|-----|
| Provider | `OpenAI` (Ollama 相容) |
| Base URL | `http://localhost:11434/v1` |
| API Key | (留空或填 `ollama`) |
| Model | `qwen:7b-vision-q5_K_M` |
| Priority | `100` (低優先度；作備選) |
| Monthly Budget | (不限，留空) |
| Allow Private Network | ✓ (必須勾選，因為是本地址) |

**模型選擇**：

| 模型 | 大小 | 準度 | 速度 | 需求 |
|------|-----|------|------|------|
| `qwen:7b-vision-q5_K_M` | 5GB | 65% | 慢(20s/張) | GPU 推薦 |
| `llava:latest` | 6GB | 60% | 慢(30s/張) | GPU 推薦 |
| `deepseek-v2:16b` | 10GB | 70% | 很慢 | 高端 GPU |

**硬體建議**：
- GPU: NVIDIA A100 / RTX 4090 (快速), RTX 3080 (可接受), 無 GPU (不推薦，非常慢)
- 記憶體: ≥ 8GB RAM + 2GB VRAM
- 磁碟: ≥ 15GB 空間

**局限**：本地模型準度較低，建議僅用於「純手動模式」（AI 作輔助，非依賴）。

## 3. 故障轉移 (Failover) 與優先度

### 優先度設定

每個提供商有 `priority` 欄位（0～100，預設 0）：
- **數字越小，優先度越高**
- 系統依序嘗試，直到成功

**建議設定**：
```
1. OpenAI (gpt-4o-mini): priority = 10 ← 首選 (快速、便宜、準)
2. Anthropic (haiku): priority = 20 ← 備選 (更便宜)
3. Google Gemini: priority = 30 ← 第三選 (免費額度用完再用)
4. Ollama (本地): priority = 100 ← 最後手段
```

### 自動轉移條件

- 連續 3 次超時或 HTTP 5xx
- 月預算已用完 (`monthly_budget_usd` 超額)
- 模型不支援多圖 (降級至逐張處理)

**聯動**：某提供商故障 20 分鐘，系統自動通知管理員；如無可用替代則 OCR job 標 `failed`，使用者仍可手動輸入。

## 4. 成本控制與預算

### 月預算設定

每個提供商可設定 `monthly_budget_usd`（如 50 元）：
- 系統追蹤 `cost_estimate` (基於 token 計數)
- 超過預算則停用該提供商
- Admin 收到告警，可增加預算或切換提供商

**成本範例**（2026-07）：

| 提供商 | 模型 | 每千件成本 |
|--------|------|-----------|
| OpenAI | gpt-4o-mini | US$2-3 |
| Anthropic | claude-haiku | US$1.5-2 |
| Google | gemini-2.0-flash | US$1-2 (或免費) |
| OpenRouter | mistral (免費) | US$0 |
| Ollama | 本地 | US$0 |

**每月預算建議**：
- 小型公司 (≤100件/天): $20-30
- 中型公司 (100-500件/天): $50-100
- 大型公司 (500+件/天): $200-500+

### 成本最佳化

1. **啟用「條碼優先」**
   - 系統會檢測條碼是否已取得單號，若是則 prompt 改為「只需其他欄位」
   - 可減少 30-40% 的 input tokens

2. **使用廉價模型**
   - Anthropic haiku / Google Gemini 與 gpt-4o-mini 在 OCR 上表現相近，成本更低

3. **分批處理**
   - 白天用付費提供商，晚上用本地 Ollama 或免費層
   - 降低高峰期成本

4. **監控成本**
   - Admin Dashboard 顯示 `/admin/ai-providers` 的 cost_estimate
   - 定期檢查 → 優化選擇

## 5. 隱私與安全

### 照片傳輸

系統在送 AI 前會自動：
1. 壓縮至長邊 1280px、JPEG Q80 (標籤文字仍可辨認)
2. 原始照片保留存證（加密存放）

**隱私聲明**：使用者首次啟用 OCR 時系統會提示：
```
⚠️ 注意：您上傳的照片將傳送至 [提供商] 的伺服器進行 AI 分析。
請勿上傳包含機密資訊的照片。
詳見隱私政策: [連結至各提供商資料保留政策]
```

### 資料保留政策

各提供商對於透過 API 傳入的圖像之保留政策：

| 提供商 | 保留政策 | 說明 |
|--------|--------|------|
| OpenAI | 30 天後刪除 | [Policy](https://openai.com/policies/api-data-usage-policies) |
| Anthropic | 無存儲 | 即時處理，不留副本 |
| Google | 根據專案設定 | 可選啟用「禁止日誌」 |
| Groq | 無存儲 | 即時處理 |
| Ollama | 全部本地 | 照片不上傳 |

**建議**：
- 機密文件只用本地 Ollama
- 無機密件可用任何提供商
- 若用雲端服務，諮詢法務確認是否符合個資法

### 機密件禁止 AI

系統可設定「機密件禁用 AI OCR」(`ocr_confidential_disabled`)：
- 勾選該選項 → 機密件無法發起 OCR job
- 強制手動輸入，確保敏感資訊不出內網

操作：
```
收件台 → 勾選「機密件」旗標 → 無法拍照 OCR → 只能手動輸入
```

## 6. 設定範例

### 小型公司 (純雲端，成本優先)

```yaml
# 管理後台 → AI 提供商

提供商 1:
  Provider: Anthropic
  API Key: sk-ant-xxxxx
  Model: claude-haiku-4-5
  Priority: 10
  Monthly Budget: 30 (US$)
  Is Active: ✓

提供商 2:
  Provider: OpenAI (OpenRouter)
  Base URL: https://openrouter.ai/api/v1
  API Key: sk-or-v1-xxxxx
  Model: mistralai/mistral-7b-instruct:free
  Priority: 20
  Monthly Budget: (無限制)
  Is Active: ✓
```

### 中型公司 (多重提供商)

```yaml
提供商 1:
  Provider: OpenAI
  API Key: sk-proj-xxxxx
  Model: gpt-4o-mini
  Priority: 10
  Monthly Budget: 100 (US$)
  Is Active: ✓

提供商 2:
  Provider: Anthropic
  API Key: sk-ant-xxxxx
  Model: claude-haiku-4-5
  Priority: 20
  Monthly Budget: 50 (US$)
  Is Active: ✓

提供商 3:
  Provider: Google Gemini
  API Key: AIza...
  Model: gemini-2.0-flash
  Priority: 30
  Monthly Budget: 0 (免費層優先)
  Is Active: ✓
```

### 隱私敏感組織 (本地離線)

```yaml
提供商 1:
  Provider: OpenAI (Ollama 相容)
  Base URL: http://localhost:11434/v1
  API Key: (無)
  Model: qwen:7b-vision-q5_K_M
  Priority: 10
  Monthly Budget: (無)
  Allow Private Network: ✓
  Is Active: ✓
```

## 7. 故障排除

### 症狀: "OCR_PROVIDER_DOWN"

**原因**：所有配置的提供商皆無法回應

**檢查清單**：
1. 確認提供商 API 狀態 (OpenAI Status, Anthropic, 等)
2. 檢查 API key 是否過期或被撤銷
3. 檢查月預算是否已用完
4. 確認網路連接正常
5. 查看 Admin Dashboard 的最近錯誤訊息

**解決**：
- 測試 Webhook: `POST /admin/ai-providers/{id}/test`
- 暫時禁用故障提供商，啟用備選
- 檢查伺服器日誌: `docker logs openmailroom-backend`

### 症狀: "OCR_BUDGET_EXCEEDED"

**原因**：某提供商月預算已超額

**解決**：
1. 增加預算: Admin → AI 提供商 → 編輯 → Monthly Budget
2. 或切換至更便宜的提供商
3. 檢查是否有異常高用量（可能是前端重複提交）

### 症狀: OCR 結果準度低

**原因**：
- 模型等級太低 (用了 haiku 或本地 Qwen)
- 照片品質差 (模糊、低光)
- 提示詞不匹配 (郵件標籤 vs 信封)

**解決**：
1. 切換至高階模型 (gpt-4o / claude-opus)
2. 檢查前端照片質量 (光線、清晰度)
3. 確認 `mail_type` 參數正確 (letter vs parcel)
4. 檢查後處理邏輯是否被禁用

### 症狀: Ollama 連接失敗

**檢查**：
- Ollama daemon 是否執行: `ollama serve` 或 `systemctl status ollama`
- Base URL 正確: `http://localhost:11434/v1`
- 防火牆: 若 Ollama 非本機，確認 11434 連通
- 模型下載完成: `ollama list` 應顯示已安裝的模型

## 8. 成本估算表 (2026-07 行情)

### 單位成本

| 提供商 | 模型 | Input (per M tokens) | Output (per M tokens) | 每張標籤平均成本 |
|--------|------|----------------------|----------------------|------------------|
| OpenAI | gpt-4o-mini | $0.15 | $0.60 | $0.002 |
| OpenAI | gpt-4-turbo | $0.01 | $0.03 | $0.0001 (小任務) |
| Anthropic | claude-haiku | $0.08 | $0.24 | $0.0015 |
| Anthropic | claude-opus | $3.00 | $15.00 | $0.015 (貴) |
| Google | gemini-2.0-flash | $0.075 | $0.30 | $0.0015 |
| OpenRouter | 各模型混合 | 0.10-1.00 | 0.30-5.00 | $0.001-0.005 |
| Ollama | 本地 | $0 | $0 | $0 |

### 月度預算範例

| 公司規模 | 日均件數 | 推薦月預算 | 預期成本 | 建議配置 |
|---------|--------|----------|--------|---------|
| 微型 | ≤50 | $10-20 | $5-10 | Anthropic haiku + OpenRouter 免費 |
| 小型 | 50-200 | $30-50 | $20-40 | OpenAI gpt-4o-mini + Anthropic 備選 |
| 中型 | 200-1000 | $80-150 | $60-120 | 多重提供商 (主備用) |
| 大型 | 1000+ | $300-500 | $250-400 | 企業方案 + 本地 Ollama 備選 |

## 9. 無 AI Key 時的純手動模式

若組織無法或不願購買 AI 服務，系統完全支援純手動：
1. 不配置任何 AI 提供商
2. 前端仍可掃條碼 (ZXing) 取單號
3. 其他欄位由使用者手動輸入
4. 系統正常運作，只是效率較低

**此為設計之初的考量，開源使用者無需 AI 也能自主**。

## 10. 更新與最佳實踐

### 定期監控

- 每週檢查 Admin Dashboard 的成本與故障狀況
- 每月評估模型更新 (2026-07 推薦可能已過時)
- 根據準度與成本調整優先度

### 模型升級

OpenAI/Anthropic 定期釋出新模型。檢查：
1. [OpenAI Models](https://platform.openai.com/docs/models)
2. [Anthropic Models](https://docs.anthropic.com/claude/reference/models-overview)
3. 定期更新 `Model` 欄位為最新推薦版本

### 安全加固

- 定期輪換 API keys (建議每季度)
- 監控異常高成本 (可能遭入侵)
- 啟用 API key 的 IP 白名單限制
- 勿在日誌中印出完整 API key (系統已隱藏)

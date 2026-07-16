# 套版設定指南

本文件說明如何自訂 Open Mail Room 的品牌外觀與通知訊息。開源使用者只需編輯一個設定檔 `config/branding.yaml` 即可完成大部分套版工作，無需修改程式碼。

## 1. branding.yaml 完整欄位說明

設定檔位於 `config/branding.yaml`，Docker 會掛載此目錄。修改後需重啟容器使變更生效。

### 應用身份 (Application Identity)

```yaml
app_name: "Open Mail Room"
```
- **用途**：應用程式名稱，顯示於瀏覽器標籤、登入頁、郵件簽名
- **限制**：≤ 100 字元
- **預設值**：`"Open Mail Room"`

```yaml
company_name: "範例股份有限公司"
```
- **用途**：組織名稱，顯示於通知訊息、報表頁尾、機構標識
- **限制**：≤ 255 字元
- **預設值**：`"範例股份有限公司"`

### Logo 設定

```yaml
logo: "./config/logo.svg"
```
- **用途**：公司商標，顯示於導航欄、登入頁、PDF 匯出
- **路徑**：相對於 `config/` 目錄
- **支援格式**：
  - **SVG** (推薦) — 可縮放、檔案小
  - **PNG** (≤ 500KB) — 需指定 `logo.png`
  - **WebP** — 現代瀏覽器支援
- **建議尺寸**：
  - 原始寬高比至少 2:1（橫向）
  - 導出後會自動縮放至 40px 高度
- **透明度**：支援 alpha 通道；淺色背景建議白底 logo，深色背景建議暗色 logo（深色模式自動反轉）

### 色彩主題 (Color Theme)

```yaml
primary_color: "#0072B2"
```
- **用途**：品牌主色，用於按鈕、連結、強調元件
- **格式**：十六進位 RGB 色碼 (e.g., `"#0072B2"`)
- **無障礙要求**：
  - 與白底對比度需 ≥ 4.5:1 (視力 20/20 正常標準)
  - 如使用深色模式，與 `#1A1A1A` 對比度需 ≥ 7:1
  - 啟動時系統會檢查；不符合則發出警告（應用仍可執行，但需調整）
- **Okabe-Ito 色盲安全推薦色盤**：
  - 藍色: `#0072B2` (推薦預設)
  - 橘色: `#E69F00` (温暖替代)
  - 綠色: `#009E73` (安寧替代)
  - 天藍: `#56B4E9` (淺色替代，不建議作主色)

**狀態色 (固定，不可改)**：
```
待確認 (pending):   #E69F00 (橘色)
已通知 (notified):  #56B4E9 (天藍)
已領取 (picked_up): #009E73 (綠色)
提醒 (reminder):    #F0E442 (黃色)
滯留/錯誤 (error):  #D55E00 (紅橙)
交寄 (outbound):    #CC79A7 (紫色)
文字 (text):        #000000 (黑) / #FFFFFF (白)
```

**為何狀態色不可改**？
- 狀態色遵循 Okabe-Ito 國際色盲安全標準，確保色盲人士 (8% 男性、0.5% 女性) 仍能區分狀態
- WCAG AAA 無障礙規範禁止顏色為唯一訊息載體，系統同時搭配圖示、文字，但色盤須維持一致性
- 因此只開放品牌主色自訂，狀態色鎖定

### 本地化 (Localization)

```yaml
locale: "zh-TW"
```
- **支援**：
  - `"zh-TW"` — 繁體中文 (台灣)
  - `"en"` — English
- **用途**：決定預設語言、日期格式、數字格式、幣別等
- **新增語言**：見本文 §4

### 操作設定 (Operational Settings)

```yaml
pickup_location: "一樓櫃台"
```
- **用途**：實體領取地點，顯示於收件人通知訊息、領取頁面
- **範例**：`"一樓櫃台"`, `"B1F 郵務中心"`, `"行政樓 3F"`
- **最大長度**：255 字元

```yaml
retention_years: 5
```
- **用途**：郵件保留年限，用於資料保留政策與自動銷毀排程
- **說明**：超過此年限的記錄與附件自動匿名化處理（符合 GDPR / 台灣個資法）
- **合規注意**：
  - 台灣公司法: 帳簿憑證至少保留 5 年
  - 個資法: 特定目的達成後應儘速銷毀，除非法律有其他規定
  - 建議與法務/資訊安全團隊確認
- **預設值**：`5` (年)

### 功能開關 (Feature Flags)

```yaml
features:
  outbound: true           # 交寄模組 (outbound shipment)
  cod: true                # 貨到付款 (Cash On Delivery)
  refrigeration: true      # 冷藏標記
  confidential: true       # 機密件處理
  analytics: true          # 分析儀表板
  two_factor_auth: true    # 雙因子認證 (2FA/TOTP)
  api_keys: true           # API 密鑰管理
```

- **用途**：開啟/關閉特定功能，減少複雜性
- **預設**：全數啟用
- **修改後**：重啟容器生效
- **說明**：
  - `outbound` — 關閉則隱藏交寄 UI 與端點
  - `cod` — 關閉則無法記錄貨到付款
  - `refrigeration` — 關閉則隱藏冷藏旗標
  - `confidential` — 關閉則機密件功能禁用
  - `two_factor_auth` — 關閉則無法啟用 2FA
  - `api_keys` — 關閉則無法管理第三方 API key

### 通知模板 (Notification Templates)

```yaml
notify_templates:
  received: |
    您的郵件/包裹已於 {received_date} {received_time} 送達 {pickup_location}。
    追蹤號碼：{tracking_number}
    寄件人：{sender_name}
    請在 {reminder_days} 天內領取。
```

通知模板支援以下變數 (使用 `{variable}` 語法)：

| 變數 | 事件 | 說明 | 範例 |
|------|------|------|------|
| `{pickup_location}` | 全部 | 領取地點 (來自 `pickup_location`) | `"一樓櫃台"` |
| `{received_date}` | `received` | 收件日期 (YYYY-MM-DD) | `"2026-07-09"` |
| `{received_time}` | `received` | 收件時間 (HH:MM) | `"10:00"` |
| `{tracking_number}` | `received`, `reminder`, `shipped` | 單號 | `"2207123456789"` |
| `{sender_name}` | `received` | 寄件人姓名 | `"ABC 物流"` |
| `{recipient_name}` | `received` | 收件人姓名 | `"王小明"` |
| `{days_unclaimed}` | `reminder` | 未領天數 | `"3"` |
| `{reminder_days}` | `received` | 提醒天數設定 | `"2"` |
| `{retention_days}` | `unclaimed` | 保留天數 | `"7"` |
| `{contact_phone}` | `reminder` | 聯絡電話 (來自 `contact.support_phone`) | `"+886-2-1234-5678"` |
| `{contact_email}` | `unclaimed` | 聯絡信箱 (來自 `contact.support_email`) | `"mailroom@example.com"` |
| `{shipped_date}` | `shipped` | 出貨日期 | `"2026-07-09"` |
| `{estimated_delivery}` | `shipped` | 預計送達 | `"2026-07-12"` |

**預設模板**（如未設定則使用）：

```yaml
received: |
  📦 您的 {tracking_number} 已送達 {pickup_location}。
  寄件人：{sender_name}
  請在 {reminder_days} 天內領取。

reminder: |
  提醒：您的包裹（{tracking_number}）已在 {pickup_location} {days_unclaimed} 天。
  請盡快前往領取。

unclaimed: |
  您的包裹（{tracking_number}）超過 {retention_days} 天未領，將進行後續處理。

shipped: |
  您的交寄單（{tracking_number}）已於 {shipped_date} 寄出。
  預計送達：{estimated_delivery}
```

**機密件模板**（自動，無法自訂）：
- 隱藏 `{sender_name}` 與內容描述
- 只提示收件人有郵件待領，需親臨現場確認

### 文件欄位設定 (Document Settings)

```yaml
document_fields:
  recipient_department: true
  sender_company: true
  reference_number: true
  signature_capture: true
  damage_photos: true
  cod_amount: true
  refrigeration_flag: true
```

- **用途**：控制 CSV/Excel 匯出與表單中顯示的欄位
- **值**：`true` (顯示) / `false` (隱藏)
- **說明**：
  - `recipient_department` — 顯示收件人部門
  - `sender_company` — 顯示寄件人公司名稱
  - `reference_number` — 顯示參考號碼
  - `signature_capture` — 顯示簽名欄
  - `damage_photos` — 顯示損毀照片欄
  - `cod_amount` — 顯示貨到付款金額
  - `refrigeration_flag` — 顯示冷藏旗標

### 聯絡資訊 (Contact Information)

```yaml
contact:
  support_email: "mailroom@example.com"
  support_phone: "+886-2-1234-5678"
  help_url: "https://example.com/mailroom-help"
  feedback_url: "https://example.com/feedback"
```

- **用途**：顯示於錯誤訊息、頁尾、說明連結
- **說明**：
  - `support_email` — 技術支援信箱
  - `support_phone` — 技術支援電話
  - `help_url` — 說明文件連結
  - `feedback_url` — 回饋/問題回報連結

### 進階設定 (Advanced / Internal)

```yaml
api_rate_limit_per_minute: 60
```
- 每個 API key 的請求速率限制（次/分）
- 預設: 60

```yaml
session_timeout_minutes: 60
```
- 會話不活動超時時間
- 預設: 60 分鐘

```yaml
allow_api_branding_changes: false
```
- 是否允許透過 API 修改套版設定
- `false` (推薦) — 只能編輯檔案修改
- `true` — 管理員可透過 API 修改

```yaml
experimental_features: false
```
- 啟用實驗性功能（開發用）
- 生產環境建議保持 `false`

## 2. Logo 規格與最佳實踐

### SVG Logo

**推薦格式**

```xml
<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
  <!-- 確保有 viewBox，便於自動縮放 -->
  <path d="..." fill="currentColor"/>
</svg>
```

- 使用 `viewBox` 而非固定寬高
- 用 `currentColor` 讓 CSS 控制顏色
- 刪除不必要的元數據和定義

**最佳尺寸**：寬高比 2:1～4:1（橫向）

### PNG Logo

- 格式：PNG-32 (RGBA)
- 大小：≤ 500KB
- 尺寸：建議 800×400px 以上（高 DPI）
- 背景：透明 (alpha channel)

### Logo 色彩適應

系統自動適應亮色/深色模式：

**亮色模式**：深色 logo (如黑色/深藍)
```css
filter: brightness(0.2);  /* 如需則變暗 */
```

**深色模式**：淺色 logo (自動反轉)
```css
filter: invert(1) brightness(1.2);  /* 反轉 + 調亮 */
```

## 3. 色彩無障礙與驗證

### 對比度檢查 (自動於啟動時執行)

系統啟動時自動驗證 `primary_color`：

```
Contrast Ratio = (L1 + 0.05) / (L2 + 0.05)
where L = (R*0.2126 + G*0.7152 + B*0.0722) / 255
```

- **WCAG AA** 最小: 4.5:1 (文字), 3:1 (UI 元件)
- **WCAG AAA** (推薦): 7:1 (文字), 4.5:1 (UI 元件)

**驗證失敗的警告日誌**：
```
[WARN] Branding color #FF00FF does not meet WCAG AAA contrast ratio (2.3:1).
       Recommended colors: #0072B2, #E69F00, #009E73
       The system will continue with defaults for inaccessible colors.
```

### 手動驗證工具

使用線上工具檢查對比度：
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [Coolors Contrast Checker](https://coolors.co/contrast-checker)

### Okabe-Ito 色盲安全色盤使用指南

| 色盤 | Hex | 用途 | 說明 |
|------|-----|------|------|
| Orange | #E69F00 | 待確認狀態、溫暖亮點 | 所有色盲類型都能區分 |
| Sky Blue | #56B4E9 | 已通知狀態、資訊 | 安寧、溫和 |
| Green | #009E73 | 已領取、成功 | 常見、自然 |
| Yellow | #F0E442 | 提醒、警告 | 高對比，僅作填色而非文字 |
| Blue | #0072B2 | 主色、連結、重要 | 深度、專業 |
| Vermillion | #D55E00 | 錯誤、滯留 | 緊急、需注意 |
| Purple | #CC79A7 | 交寄、特殊 | 差異化、女性友善 |

**文字配色規則**：

| 底色 | 適合文字色 | 對比度 |
|------|-----------|--------|
| #F0E442 (黃) | #000000 (黑) | 17.1:1 ✓ |
| #56B4E9 (天藍) | #000000 (黑) | 8.6:1 ✓ |
| #E69F00 (橘) | #000000 (黑) | 9.3:1 ✓ |
| #009E73 (綠) | #FFFFFF (白) | 7.5:1 ✓ |
| #0072B2 (藍) | #FFFFFF (白) | 8.9:1 ✓ |

## 4. 多語言支援

### 目前支援語言

- `zh-TW` — 繁體中文 (台灣)
- `en` — English

### 新增語言步驟

1. **建立語言檔案**

```bash
mkdir -p frontend/locales
cp frontend/locales/zh-TW.json frontend/locales/your-lang.json
```

2. **編輯語言檔案** (JSON 格式)

```json
{
  "common": {
    "app_name": "Open Mail Room",
    "company_name": "Example Corp",
    "logout": "Sign Out"
  },
  "pages": {
    "login": {
      "title": "Login",
      "email": "Email",
      "password": "Password"
    }
  }
}
```

3. **修改 branding.yaml**

```yaml
locale: "your-lang"
```

4. **更新前端設定** (`frontend/vite.config.ts` 或 vue-i18n 配置)

```typescript
import yourLang from './locales/your-lang.json'

const i18n = createI18n({
  legacy: false,
  locale: config.locale,
  messages: {
    'your-lang': yourLang
  }
})
```

5. **重新建構並重啟容器**

```bash
docker-compose down
docker-compose up -d
```

### 翻譯提交

如欲貢獻新語言或修正翻譯，請：
1. Fork 本專案
2. 提交翻譯檔案至 `frontend/locales/`
3. 建立 Pull Request

社群貢獻歡迎！

## 5. 套版驗證清單

修改 `branding.yaml` 後，重啟容器前請檢查：

- [ ] `app_name` 和 `company_name` 已設定
- [ ] Logo 檔案存在於 `config/` 目錄且格式正確
- [ ] `primary_color` 為有效的十六進位色碼
- [ ] `primary_color` 對比度警告已處理（或選用推薦色）
- [ ] `locale` 為支援的語言 (`zh-TW` 或 `en`)
- [ ] `pickup_location` 已確認
- [ ] `retention_years` 符合公司政策與法律規定
- [ ] 功能開關 (`features`) 已按需求設定
- [ ] 通知模板 (若自訂) 包含所需變數
- [ ] 聯絡資訊 (`contact`) 已更新為正確信箱/電話
- [ ] YAML 語法無誤（可用線上 [YAML Validator](https://www.yamllint.com/) 檢查）

## 6. 常見問題

**Q: 修改 branding.yaml 後何時生效？**
A: 需重啟 Docker 容器。快速方式：
```bash
docker-compose restart backend frontend
```

**Q: 能否在執行時修改套版設定？**
A: 不建議。若 `allow_api_branding_changes: true`，可透過 API 修改，但重啟後會被檔案覆蓋。推薦永遠編輯檔案。

**Q: 我的 Logo 在深色模式下看不清楚？**
A: 確保 Logo 使用透明背景，系統會自動反轉顏色。SVG 建議用 `currentColor`，PNG 需高對比度。

**Q: 如何在通知中隱藏寄件人資訊？**
A: 建立收件時勾選 `is_confidential: true`，系統會自動使用機密件模板。

**Q: 能自訂狀態色嗎？**
A: 不行。狀態色是固定的，以確保無障礙合規。只能自訂 `primary_color`。

**Q: 新增語言需多久？**
A: 翻譯全量字符串約 1-2 小時（約 500 詞條）；提交後納入下版發佈。

# 06 UI/UX 規格(RWD、PWA、相機、無障礙、套版)

## 1. 頁面清單

| 頁面 | 主要對象 | 重點 |
|---|---|---|
| 登入 | 全部 | 支援 2FA(可選) |
| 收件台(首頁) | counter | 大按鈕:拍照登記/批次上傳/領取核銷;今日待確認、待領取清單 |
| 拍照登記 | counter | 相機即時預覽 + ZXing 即時掃碼框;連拍模式 |
| OCR 確認 | counter | 左圖右表(手機上下堆疊),欄位可改,員工比對候選 chips |
| 領取核銷 | counter | 搜姓名/掃員工 QR/輸入取件碼 → 觸控簽名板 |
| 交寄 | counter/employee | 表單 + 拍託運單 |
| 我的郵件 | employee | 自己的待領/歷史;綁定通知 |
| 查詢/報表 | counter/viewer | 篩選、匯出、圖表 |
| 管理後台 | admin | AI Key、通知通道、名錄、部門、webhook、稽核、品牌設定 |

## 2. RWD / PWA

- Mobile-first;斷點 640/1024;櫃台手機是主戰場,桌機是查詢報表主場。
- vite-plugin-pwa:`manifest.webmanifest`(名稱/圖示吃 branding 設定)、service worker precache、**離線佇列**:無網路時拍的照片與表單存 IndexedDB,恢復連線自動補送(收發室常在地下室,此為必要功能)。
- 相機:`<input type="file" accept="image/*" capture="environment">` 為基準(iOS/Android 皆穩);進階即時掃碼用 `getUserMedia`(需 HTTPS;iOS Safari 16.4+ PWA 支援)。兩者都做,getUserMedia 不可用時自動降級。
- iOS 注意:PWA 推播 iOS 16.4+ 才支援且需加入主畫面;Web Push 列 v1.5。

## 3. 無障礙(WCAG 2.2 AAA 對比)與配色

- 文字對比 ≥7:1(大字 ≥4.5:1);非文字 UI 元件 ≥3:1。
- **顏色永不作為唯一訊息載體**:狀態一律「色點 + 圖示 + 文字」。
- 觸控目標 ≥44×44px;完整鍵盤導航;`prefers-reduced-motion` 尊重;表單錯誤具體描述。
- Okabe-Ito 色盲安全色盤(固定 token,套版只能換「主品牌色」,狀態色不開放改以保護無障礙):

| Token | Hex | 用途 |
|---|---|---|
| oi-orange | #E69F00 | 待確認 |
| oi-skyblue | #56B4E9 | 已通知 |
| oi-green | #009E73 | 已領取 |
| oi-yellow | #F0E442 | 提醒(僅底色,配黑字) |
| oi-blue | #0072B2 | 主要動作/連結 |
| oi-vermillion | #D55E00 | 滯留/錯誤 |
| oi-purple | #CC79A7 | 交寄 |
| black/white | #000000 / #FFFFFF | 文字/底 |

- 注意:黃、天藍、橘在白底上當「文字」不足 AAA——這些色只用於填色塊/圖表/badge 底色,文字一律黑(#000 on #F0E442 ≈ 17:1)或用加深變體;正文文字用 #1A1A1A on #FFFFFF(≈17:1)。深色模式同理鏡射。CI 加自動對比檢查(見 08 測試)。

## 4. 套版設定檔(開源使用者唯一需要動的地方)

`config/branding.yaml`:
```yaml
app_name: "Open Mail Room"
company_name: "範例股份有限公司"
logo: "./config/logo.svg"
primary_color: "#0072B2"     # 會自動驗證對比,不合格啟動時警告
locale: "zh-TW"              # zh-TW | en
pickup_location: "一樓櫃台"
retention_years: 5
features:
  outbound: true
  cod: true
  refrigeration: true
  confidential: true
notify_templates:            # 可覆寫 05 的預設模板
  received: "..."
```
Docker volume 掛載 `./config`,改完 restart 即生效。i18n 用 vue-i18n,文案全部進語系檔,新增語言=新增一個 JSON。

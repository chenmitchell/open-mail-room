# Open Mail Room 開源收發室系統 — 規劃文件組

> 版本 1.0|2026-07-09|規劃者:Claude Fable 5|狀態:規劃完成,待執行
> 專案代號 `openmailroom`(套版者可改名,見 06 品牌設定)

## 一句話定位

自架(self-hosted)、開源的公司櫃台收發登記系統:手機/網頁拍照 → 條碼掃描 + AI OCR 自動填表 → 人工確認 → 儲存 → 自動通知收件人(LINE/Telegram/Slack/Email/Webhook)→ 領取簽收核銷。支援台灣常見郵件、快遞、貨運通路,含交寄(outbound)登記。BYOK(自帶 AI Key)、RWD、PWA、WCAG AAA、Okabe-Ito 色盲安全色盤。

## 市場空缺(調查結論,詳見 10-RESEARCH.md)

商用產品(Notifii/PackageX/Envoy/Parcel Tracker)功能成熟且高度同質,證明需求真實;但**開源界沒有任何活躍可部署的同類方案**,台灣市場只有閉源社區 App(智生活等)。「拍標籤→LLM Vision→名錄比對→通知→簽收」流程開源零實作。

## 文件索引(執行 AI 必讀順序)

| 檔案 | 內容 | 執行時機 |
|---|---|---|
| README.md | 總覽、技術決策、入口指令 | 每個 session 開始必讀 |
| 01-REQUIREMENTS.md | 角色、流程、櫃台紀錄欄位、驗收標準 | M1 前必讀 |
| 02-DATA-MODEL.md | 資料庫 schema | M1 |
| 03-API-SPEC.md | REST API、Webhook、事件 | M1–M3 |
| 04-AI-OCR.md | AI Provider 抽象層、BYOK、Prompt、條碼優先策略 | M2 |
| 05-NOTIFICATIONS.md | 通知通道 adapter(LINE Messaging API 等) | M3 |
| 06-UI-UX.md | RWD/PWA/相機/配色/i18n/套版設定檔 | M1、M5 |
| 07-SECURITY.md | TLS、靜態加密、RBAC、上傳安全、金鑰管理 | 全程遵守 |
| 08-EXECUTION-PLAN.md | 里程碑、子代理分工、無人值守開發循環、Code Review 協議 | 全程 |
| 09-HANDOFF.md | Session 交接協議、PROGRESS/DECISIONS 紀錄規範 | 每個 session 開始/結束 |
| 10-RESEARCH.md | 開源/商用調查、台灣物流通路與單號格式表 | 參考 |
| 11-GAPS-AND-ADVICE.md | 盲點清單與設計取捨 | 參考 |

## 已定案的技術決策(不要在執行時重新辯論;要推翻先寫入 DECISIONS.md)

| 項目 | 決策 | 理由 |
|---|---|---|
| 後端 | Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic | 使用者選定;Python 生態最適合 OCR/AI 整合 |
| 前端 | Vue 3 + Vite + TypeScript + Pinia + vite-plugin-pwa | 使用者選定;PWA 支援成熟 |
| 資料庫 | SQLite(預設,零設定)/ PostgreSQL(環境變數切換) | 降低自架門檻 |
| 部署 | Docker Compose 一鍵部署為主;Caddy 反代自動 HTTPS | 使用者選定 |
| 任務佇列 | 內建 async background tasks(小規模);預留 arq/Redis 介面 | 避免強制依賴 Redis |
| 條碼掃描 | 前端 ZXing(@zxing/browser)優先,免 AI token | 省成本、更準 |
| AI OCR | 後端統一呼叫,支援 OpenAI / Anthropic / Google / OpenRouter / 任意 OpenAI-compatible endpoint | 見 04 |
| 通知 | Adapter 模式:LINE Messaging API、Telegram、Slack、Discord、Email、通用 Webhook、Web Push | LINE Notify 已於 2025/3/31 停用,勿使用 |
| 授權 | AGPL-3.0(建議,見 11 的討論) | 防止閉源 SaaS 拿走不回饋 |
| i18n | zh-TW 預設 + en,vue-i18n | 開源國際化 |
| 無人值守 | 依 08-EXECUTION-PLAN.md 的循環:實作代理 → 測試 → 審查代理 Code Review → 修正 → 記錄 → 下一項 | 使用者要求 |

## 給執行 AI 的入口指令(任何模型:Fable / Opus / Sonnet 皆適用)

```
你是 Open Mail Room 的執行工程師。規則:
1. 先讀 openmailroom-plan/README.md、09-HANDOFF.md、PROGRESS.md(若存在)、DECISIONS.md(若存在)。
2. 從 PROGRESS.md 找到目前里程碑與下一個未完成任務;若無 PROGRESS.md,從 08-EXECUTION-PLAN.md 的 M0 開始並建立 PROGRESS.md。
3. 每完成一個任務:跑測試 → 派審查子代理做 Code Review(標準見 08 §5)→ 修正 → 更新 PROGRESS.md。
4. 所有重大取捨寫入 DECISIONS.md(格式見 09)。
5. 全程遵守 07-SECURITY.md 與 06-UI-UX.md 的無障礙規範。
6. 不確定的規格以 01~07 文件為準;文件沒寫的,選最保守方案並記錄。
7. Session 結束前必須完成 09-HANDOFF.md 的「交接檢查清單」。
```

## 驗收定義(整個專案完成的標準)

`docker compose up` 後:手機瀏覽器開啟 → 安裝 PWA → 拍包裹照片(或批次上傳)→ 條碼自動辨識單號、AI OCR 填入寄件人/收件人 → 收件人自動比對到員工名錄與部門 → 人工確認儲存 → 收件人收到 LINE/Email 通知 → 領取時簽名核銷 → 全程紀錄可查詢匯出;交寄流程同樣可用;更換 `config/branding.yaml` 與 logo 即成為另一家公司的系統;API 文件(OpenAPI)可供第三方串接;測試覆蓋率後端 ≥80%;Lighthouse PWA/Accessibility 皆 ≥90。

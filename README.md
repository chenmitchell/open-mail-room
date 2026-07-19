# Open Mail Room

**開源、可自架的公司收發室系統。** 櫃台用手機拍一張包裹標籤,AI 讀出收件人與單號,系統自動通知本人來領,領取時簽名存證。

專為台灣辦公室設計:中文姓名模糊比對、部門件轉交、中華郵政與各家宅配單號格式、超商取貨、代收貨款(COD)、冷藏件。

**原作者 / Original author:** [Mitchell Chen](https://github.com/chenmitchell) · 更多作品見 [github.com/chenmitchell](https://github.com/chenmitchell)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Author: Mitchell Chen](https://img.shields.io/badge/Author-Mitchell%20Chen-181717?logo=github)](https://github.com/chenmitchell)

---

## 為什麼會有這個東西

大部分公司的收發室是一本簿子 + 一個 LINE 群組。包裹堆在櫃台,收件人不知道東西到了,櫃台不知道誰領走了,離職的人的信件沒人處理,冷藏品放到壞掉。要查「三個月前那份合約什麼時候簽收的、誰簽的」,基本上查不到。

Open Mail Room 把這件事變成:**拍照 → 確認 → 通知 → 領取簽收**,每一步都有紀錄。

---

## 它怎麼運作

```
   送達            登記             通知               領取
    │               │                │                  │
  快遞放下 ───▶ 櫃台拍標籤 ───▶ 本人收到訊息 ───▶ 來櫃台簽名帶走
                    │
               AI 讀出收件人、
               單號、寄件人
                    │
               櫃台看一眼確認
```

櫃台的實際動作是:**拍一張照 → 看一眼 → 按送出**,大約 3 秒。剩下的事系統自己做。

### 一句話設計原則:AI 負責填空,人負責決定

AI 讀錯的代價必須是「櫃台改一個欄位」,而不是「包裹送錯人」。所以:

- 每一件都會經過確認畫面,**低信心的欄位標黃**提醒
- 收件人有兩位以上同樣高分的候選(例如公司有兩個「陳怡君」),系統**不會替你猜**,而是把候選留給人點 —— 多按一下,好過一封信送錯人
- 沒有「自動確認」這個選項。這不是還沒做,是刻意的

### 為什麼是「專為台灣」

不是翻譯問題,是這些東西在別的地方不存在:

- **中文姓名模糊比對**,而且比對別名 —— 台灣辦公室很多信是靠綽號在流通的
- **部門件**:信封寫「財務部 收」而不是人名,系統比對到部門、通知該部門的固定聯絡人
- **中華郵政 14/20 碼**、掛號/限時/快捷/包裹的類別碼、各家宅配與電商的單號格式
- **超商取貨**、**代收貨款**、**冷藏件**

---

## 適合誰

- **10–500 人的辦公室**,每天幾件到幾十件包裹
- 想要**資料留在自己手上**:自架、SQLite 就夠、照片加密存放,甚至可以用本地 Ollama 讓照片完全不出公司
- 需要**查得到紀錄**:誰在什麼時候領走了什麼,有簽名存證

**不適合**:物流倉儲、大型集散中心。這是辦公室櫃台的工具,不是 WMS。

---

## 功能

**收件登錄**
- 手機直接拍照(PWA,免安裝),或批次上傳最多 30 張
- AI OCR 讀出:收件人、寄件人、單號、承運商、COD 金額。低信心欄位會標黃,由櫃台人工確認 —— **AI 只負責填空,不負責決定**
- 條碼/QR 掃描輔助帶入單號
- 支援 HEIC(iPhone 預設格式)
- 記錄照片的 EXIF 拍照時間;GPS 等其餘 EXIF 一律剝除

**收件人比對**
- 中文姓名模糊比對員工名錄(含別名/綽號),回候選清單讓櫃台選
- 部門件:信件寫的是公司/部門而非人名時,自動比對部門並通知該部門的固定聯絡人

**通知**
- Email、LINE、Slack、Discord、Telegram、自訂 Webhook
- 員工自行綁定通知管道(綁定碼驗證)
- 未領取自動催領、逾期未領告警、失敗自動重試 + 死信清單

**領取**
- 取件碼查詢、螢幕簽名存證、代領記錄
- 機密件:限定角色可見,每次檢視都留稽核紀錄

**登記錯了**
- **作廢**(需填理由):離開待領清單、排除在報表統計外,但**紀錄與稽核軌跡保留**
- 沒有刪除功能,是刻意的 —— 能憑空消失的紀錄會把自己的歷史一起帶走
- 已領取的件不能作廢:那個簽名記錄的是真的發生過的事

**交寄(寄出)**
- 交寄單、託運單號登錄(可拍照 OCR)、寄出通知

**管理與稽核**
- 角色權限:admin / counter(櫃台)/ employee(員工)/ viewer
- 報表:期間統計、部門/承運商/日別分組、CSV 匯出
- 完整稽核軌跡(誰在何時改了什麼)
- 保存期限到期自動匿名化

**離線可用**
- 網路斷了照樣能拍照登錄,排入佇列,連線後自動送出

---

## 安全

這個系統存的是同事的個資和信件內容,所以:

- **欄位加密**:Email、電話等個資以 AES-256-GCM 加密存放,支援金鑰輪替
- **檔案加密**:上傳的照片與簽名檔加密後才落地
- **EXIF 剝除**:照片的 GPS 位置屬個資,一律在入口就砍掉(只保留拍照時間)
- **密碼**:argon2id
- **上傳防護**:魔數驗證(不信任副檔名/Content-Type)、Pillow 重新編碼消毒、解壓縮炸彈防護、單檔 15MB / 單批 30 張上限
- **CSRF**:double-submit token;Session 走 HttpOnly cookie
- **SSRF 防護**:Webhook / 自架 AI 端點預設拒連內網位址
- **AI 金鑰**:加密存放,不會出現在前端或 log

> **極重要**:`ENCRYPTION_KEY` 遺失 = 所有加密照片與個資永久無法讀取。部署後**立刻備份**,且備份不要跟伺服器放同一個地方。詳見 [docs/INSTALL.md](docs/INSTALL.md#密鑰備份重要)。

---

## 快速開始

### Docker Compose(建議)

```bash
git clone https://github.com/YOUR-USERNAME/open-mail-room.git
cd open-mail-room/deploy
chmod +x deploy.sh
DOMAIN=mailroom.example.com ./deploy.sh
```

腳本會自動產生金鑰、提醒你備份、拉映像、起服務、自動申請 HTTPS 憑證。

內網自簽憑證版本與 PostgreSQL 選項見 [docs/INSTALL.md](docs/INSTALL.md)。

### Zeabur(單一容器)

見 [docs/DEPLOY-ZEABUR.md](docs/DEPLOY-ZEABUR.md)。

### 第一次啟動

`deploy.sh` 會**隨機產生一組管理員密碼並印在終端機上(只印這一次)**,管理員帳號在你開站前就已經建好了 —— 所以你看到的是登入頁,不是設定精靈。用那組密碼登入,然後**立刻改密碼**。

(如果你是自己設定環境變數而沒給 `ADMIN_PASSWORD`,那就會看到初始設定精靈,由你自己決定密碼。)

登入後依序:

1. **匯入員工名錄**(CSV)或手動新增 —— 沒有名錄,姓名比對就沒有對象可比。記得填別名/綽號
2. **設定部門與各部門的固定聯絡人** —— 沒有聯絡人的部門收不到部門件的通知
3. 到「**AI 設定**」填入你自己的 AI 供應商 API 金鑰
4. **設定通知管道**,並請同事各自去「通知設定」綁定

完整操作流程見 **[docs/USAGE.md](docs/USAGE.md)**。

---

## AI OCR

**你要自己準備 AI 供應商的 API 金鑰。** 系統本身不含、也不代付任何 AI 費用。

支援:OpenAI、Anthropic Claude、Google Gemini、OpenRouter,以及**本地 Ollama**(完全離線,照片不出公司)。

可同時設定多家並排優先度,前者失敗自動轉下一家。詳見 [docs/AI-PROVIDERS.md](docs/AI-PROVIDERS.md)。

---

## 客製

不用改程式:編輯 `config/branding.yaml` 就能換公司名、Logo、主色、取件地點、保存年限、通知範本、功能開關(交寄/COD/冷藏/機密件/2FA…)。詳見 [docs/BRANDING.md](docs/BRANDING.md)。

---

## 技術架構

| | |
|---|---|
| 後端 | Python 3.12 / FastAPI / SQLAlchemy 2 (async) / Pydantic v2 / Alembic |
| 前端 | Vue 3 / Vite / TypeScript / Pinia / vue-i18n / PWA |
| 資料庫 | SQLite(預設,免額外服務)或 PostgreSQL |
| 部署 | Docker Compose + Caddy(自動 HTTPS),或單一容器(Zeabur 等) |

AI 供應商一律以原生 REST 呼叫(httpx),不綁任何廠商 SDK —— 換供應商不用改架構。

---

## 文件

| | |
|---|---|
| **[USAGE.md](docs/USAGE.md)** | **每天怎麼用** —— 櫃台、員工、管理員的完整操作流程 |
| [INSTALL.md](docs/INSTALL.md) | 安裝、金鑰備份、升級、還原、故障排除 |
| [AI-PROVIDERS.md](docs/AI-PROVIDERS.md) | AI 供應商設定與故障轉移 |
| [BRANDING.md](docs/BRANDING.md) | 品牌與功能開關客製 |
| [API-INTEGRATION.md](docs/API-INTEGRATION.md) | 對外 API 與 Webhook 串接 |
| [FAQ.md](docs/FAQ.md) | 常見問題 |
| [docs/plan/](docs/plan/) | 完整規格:需求、資料模型、API、OCR、通知、UI/UX、安全 |

---

## 開發

```bash
# 後端
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m pytest              # 全部測試
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
npm test
```

時間一律以 UTC 存、以台北時間顯示。所有 API 回傳的時間都帶時區偏移。

---

## 授權與署名

[GNU AGPL v3](LICENSE),**外加一條 AGPL 第 7(b) 署名條款**(見 [NOTICE](NOTICE))。

白話:

- 你可以自架、自用、改它、商業使用,公司內部用完全不受限制。
- 如果你把改過的版本**架成對外服務給別人用**,你必須把你的修改也開源出來(這是 AGPL)。
- **不論你怎麼用或怎麼改,都必須保留對原作者 Mitchell Chen 的署名,以及回到 [github.com/chenmitchell/open-mail-room](https://github.com/chenmitchell/open-mail-room) 的連結** —— 包含 app 介面裡的那行作者標示。你可以改樣式配合你的品牌,但不能拿掉(這是第 7(b) 條)。

修改後的版本必須標明「你改過、以及改的日期」,且不得暗示原作者為你的修改版本背書。

---

## 原作者

**Mitchell Chen** — [github.com/chenmitchell](https://github.com/chenmitchell)

這個專案的完整開發歷程、以及其他作品,都在上面的 GitHub。歡迎回去看看。

---

## 貢獻

歡迎 Issue 與 PR。送 PR 前請確認 `pytest`、`vitest`、`ruff`、`eslint`、`vue-tsc` 都是綠的。

貢獻即表示你同意你的貢獻以本專案的授權(AGPL-3.0 + 第 7(b) 署名條款)釋出。

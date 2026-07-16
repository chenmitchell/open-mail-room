# Zeabur 部署指南(ZEABUR-1,單一容器:後端同時 serve 前端)

> 適用情境:主機是 Zeabur 代管的 K3s 節點,沒有 docker CLI、
> 80/443 由 Zeabur ingress 佔用並終止 TLS。此路徑**不是**
> `deploy/docker-compose.yml` 那套(那套是保留給自己有主機、自己跑
> docker-compose + Caddy 的自架情境,兩者互不影響、可並存於同一個
> repo)。本文件走的是根目錄 `Dockerfile`:node 階段建置前端 →
> python 階段安裝後端 + 把前端 build 產物一起包進同一個 image,
> 由後端(FastAPI/uvicorn)同時服務 API 與前端靜態檔+SPA fallback。

## 1. 前置需求
- Zeabur 帳號、已連結你的 GitHub(你 fork 的 repo(私人 repo 需先在 Zeabur 授權存取))。
- 想綁定的網域(本文以 `mailroom.example.com` 為例),DNS 可指到 Zeabur 給的位址。
- **不需要**先手動產生 `SECRET_KEY`/`ENCRYPTION_KEY`——這兩把金鑰由容器
  **首次啟動時自動產生**並寫入 `/data/secrets.env`(見第 5 節),不需要在
  Zeabur 表單裡填任何機密值。

## 2. 在 Zeabur 建立專案並部署
1. Zeabur Dashboard → 開一個新專案(或用既有專案)。
2. Add Service → Deploy from GitHub → 選你 fork 的 repo。
3. Root Directory 保持預設(repo 根目錄)——根目錄的 `Dockerfile` 會被
   Zeabur 自動偵測並使用(Zeabur 看到根目錄有 `Dockerfile` 就會用 Docker
   建置,不需要額外設定;repo 內附的 `zbpack.json`
   `{"ignore_dockerfile": false}` 只是明確表態「不要略過這個
   Dockerfile」,防止之後 repo 長出更多 `package.json`/`requirements.txt`
   之類的檔案時被誤判成用 buildpack 建置)。
4. 第一次部署前(或部署後,Redeploy 皆可)到該 Service 的設定頁掛
   Volume:掛載路徑填 `/data`。**這一步務必在正式收資料前完成**——
   SQLite 資料庫、上傳附件、自動產生的密鑰檔都存在 `/data`,沒掛
   Volume 的話容器重啟/重新部署資料就會全部消失。
5. 設定環境變數(見第 3 節),存檔後觸發部署(或等自動部署)。
6. 部署完成後,到第 4 節綁定網域;到第 6 節從 log 取出 admin 密碼與備份
   `/data/secrets.env`。

## 3. 環境變數清單
**必要**:
| 變數 | 建議值 | 說明 |
|---|---|---|
| `ENVIRONMENT` | `production` | 決定 cookie Secure 旗標、金鑰弱檢查等安全預設值,Zeabur 一定要設這個。 |

**非必要(有安全預設值,通常不用碰)**:
| 變數 | 預設 | 什麼時候才需要改 |
|---|---|---|
| `SECRET_KEY` / `ENCRYPTION_KEY` / `ENCRYPTION_KEYS` | 不設 → 容器首次啟動自動產生,寫入 `/data/secrets.env` 並在之後每次啟動沿用 | 只有「想自己掌控金鑰」或「要做金鑰輪替」時才手動設(見 `.env.example` 的 `ENCRYPTION_KEYS`/`ENCRYPTION_ACTIVE_KEY` 說明) |
| `ADMIN_EMAIL` | `admin@example.com` | 想指定初始管理員信箱時設 |
| `ADMIN_PASSWORD` | 不設 → 首次啟動由 seed 隨機產生,印一次在 log | 想指定初始密碼時設(仍建議登入後立即改密碼) |
| `DATA_DIR` | `/data` | 通常不用改,除非你把 Volume 掛在別的路徑 |
| `PORT` | `8080` | Zeabur 通常會自動注入正確的 `$PORT`;不需要手動設 |
| `SERVE_FRONTEND` | `1` | 只有「這個服務只想當純 API、前端另外找地方 serve」才設成 `0` |
| `FRONTEND_DIST` | `/app/frontend_dist` | 這是 image 內建置產物的路徑,幾乎不需要改 |
| `CORS_ALLOW_ORIGINS` | 空(同源,不開 CORS) | 前後端同源部署(本文件這條路徑)不需要設;只有前端另外部署在別的網域時才需要 |
| `DOMAIN` | - | Zeabur 版部署不使用這個變數(它是 docker-compose + Caddy 那套專用的),網域改在 Zeabur 的「Domain」設定頁綁定 |
| 通知/OCR 相關(`LINE_*`/`TELEGRAM_*`/`SMTP_*`/`OCR_PROVIDER`/`OPENAI_API_KEY`/...) | 見 `.env.example` | 要開對應功能才設,沒設系統仍可完整運作(手動登記+核銷,OCR/通知優雅失敗) |

完整變數說明與更多細節見根目錄 `.env.example`。

## 4. 綁定網域
Zeabur 專案 → 該 Service → Domain → 綁定 `mailroom.example.com`(或你的
網域),依 Zeabur 畫面指示把 CNAME/A 記錄指過去。Zeabur ingress 會自動
簽發並終止 TLS,容器本身完全不用管憑證——這也是為什麼
`scripts/entrypoint.sh` 用 `--proxy-headers --forwarded-allow-ips='*'`
啟動 uvicorn:讓 app 相信 ingress 轉過來的 `X-Forwarded-Proto: https`,
Secure cookie 才會正確生效。

## 5. 首次啟動做了什麼(自動)
容器的 `scripts/entrypoint.sh` 依序:
1. 檢查環境變數有沒有給 `SECRET_KEY`/`ENCRYPTION_KEY`(或
   `ENCRYPTION_KEYS`)。若沒有,檢查 `/data/secrets.env` 存不存在;
   不存在就用 `openssl rand -base64 32`(或退回 `python3` 產生等效隨機值)
   各產生一把,寫入 `/data/secrets.env`(`chmod 600`),並在 log 印出
   「請備份 `/data/secrets.env`」的提醒。**這個檔案只會產生一次**——
   之後每次重啟/重新部署都直接讀這個檔案沿用同一把金鑰,不會覆蓋。
2. `alembic upgrade head`(建表/更新 schema)。
3. `python3 scripts/seed.py`(冪等):建立/確認 admin 帳號、預設承運商
   清單。若沒設 `ADMIN_PASSWORD`,這一步會隨機產生一組密碼並印在 log
   (只印這一次,之後不會再印)。
4. 啟動 `uvicorn`,監聽 `$PORT`(預設 8080)。

## 6. 部署完成後立即做(不能失誤清單)
1. 到 Zeabur 的 Deployment Logs 找 `scripts/entrypoint.sh` 印出的
   admin 密碼(關鍵字找 `ADMIN_PASSWORD` 或 seed 印出的那一行),
   立刻抄到密碼管理器,並在第一次登入後改掉。
2. **備份 `/data/secrets.env`**:這個檔案遺失 = 所有使用者 session 失效
   + 既有加密資料(電話、地址、上傳照片等)永久無法解密。可以用
   Zeabur 的 Shell/Exec 功能連進容器 `cat /data/secrets.env` 抄出來,
   或用 Volume 的檔案管理介面下載(見 Zeabur 文件「File Management」)。
3. 用 `https://mailroom.example.com` 開站測登入,**不要用容器內部
   port 或 IP 直接測**——production 模式的 session cookie 帶 Secure
   旗標,非 HTTPS 開站會出現「登入成功卻馬上被登出」的假故障。
4. 打 `https://mailroom.example.com/healthz` 與 `/readyz` 確認都是
   200;`/readyz` 若回 503 通常是 migration 還沒跑完或 DB 未就緒,看
   Deployment Logs。
5. 登入 admin → 依需求設定 AI provider(OCR)、SMTP/LINE/Telegram
   (通知)——兩者都不設系統仍可完整運作,只是走手動登記/核銷,
   OCR job 與通知會優雅失敗(不會讓其他功能跟著壞)。
6. 匯入員工名錄 CSV,快速走一遍「登記 → 領取核銷 → 報表」驗收流程。

## 7. 更新版本
Push 到 GitHub 的對應分支即可觸發 Zeabur 自動重新部署(或在 Zeabur
Dashboard 手動 Redeploy)。`alembic upgrade head` 與 seed 每次啟動都會
跑一遍,是冪等的,不會重複建立資料或覆蓋既有金鑰。

## 8. 故障排查速查
- Deployment 一直重啟 / CrashLoop:看 Deployment Logs,常見原因是
  Volume 沒掛到 `/data`(entrypoint 寫入 `secrets.env` 失敗)或
  DATABASE_URL 被手動覆寫成錯誤值。
- `/readyz` 回 503:DB 未初始化或 migration 失敗,看 log 的
  `alembic upgrade head` 那段輸出。
- 登入後馬上被踢出:見第 6 節第 3 點(要用 https 網域測,不要用
  http 或裸 IP)。
- 前端顯示空白或 404:確認 image build 的 node 階段有成功產出
  `frontend/dist`(看 build log),以及 `SERVE_FRONTEND` 沒被手動設成
  `0`。
- `POST/PUT/DELETE` API 404 但頁面上其他功能正常:通常是前端呼叫的
  路徑打錯(不是 `/api/v1/...`),SPA fallback 只接手「非 API 的 GET
  請求」,`/api/*` 一律照舊回真正的 API 404 JSON 格式,不會被
  fallback 蓋掉。

## 9. 已知風險 / 尚待驗證
- **Volume 權限**:image 內以非 root 使用者(uid 1000, `appuser`)執行,
  Dockerfile 有預先 `mkdir -p /data && chown appuser /data`,但如果
  Zeabur 的 Volume 驅動在掛載一個全新 Volume 時把權限重置成
  root-only,`appuser` 可能無法寫入 `/data`(entrypoint 會在
  `mkdir -p "$DATA_DIR"` 或寫 `secrets.env` 時明確失敗於 log,不會是
  「資料悄悄不見」這種沉默失敗)。若遇到這個狀況,請回報 Zeabur
  support 詢問 Volume 的預設擁有者/UID 設定方式;開發沙盒沒有 Zeabur
  帳號可實測這一項,只做到「失敗會清楚印在 log」這個保底設計。
- **本檔案未實機驗證**:開發沙盒沒有 Docker,無法真的 build image 或
  連 Zeabur 實測整個部署流程;`Dockerfile`/`zbpack.json` 已用 Python
  腳本做過逐行靜態檢查(instruction 合法性、`COPY` 來源路徑存在、
  多階段 `--from` 參照一致),但真正的 `docker build`/`docker run`
  行為(例如 apt 套件是否都能裝、image 大小、實際啟動時間)仍需要
  在有 Docker 或有 Zeabur 帳號的環境跑一次首次部署驗證。

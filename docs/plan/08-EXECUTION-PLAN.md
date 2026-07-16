# 08 執行計畫(里程碑、子代理分工、無人值守循環、Code Review 協議)

## 1. Repo 結構

```
openmailroom/
├─ backend/            # FastAPI
│  ├─ app/{api,models,services,ocr,notify,security,tasks}/
│  ├─ alembic/  ├─ tests/  └─ pyproject.toml
├─ frontend/           # Vue 3 + Vite + TS
│  ├─ src/{pages,components,stores,composables,locales}/
│  └─ tests/
├─ config/             # branding.yaml、logo(volume 掛載)
├─ deploy/             # docker-compose.yml、Caddyfile、備份腳本、自簽憑證腳本
├─ docs/               # 安裝、套版、API 串接、個資告知範本
├─ PROGRESS.md  ├─ DECISIONS.md  └─ .github/workflows/ci.yml
```
> GitHub repo 依使用者全域規則:開發期 Private;對外發布時另建/轉 Public。

## 2. 里程碑(每個 M 完成 = 可 demo 的增量)

| M | 內容 | 完成定義(DoD) |
|---|---|---|
| M0 | 腳手架:repo、Docker Compose(backend+frontend+Caddy)、CI、healthz、登入/RBAC、branding.yaml 載入 | `docker compose up` 可登入看到空首頁;CI 綠 |
| M1 | 收件核心:carriers 種子、員工名錄+CSV 匯入+模糊比對、手動建立收件、狀態機、領取簽名核銷、查詢列表 | 不用 AI 也能完整跑收件→領取流程 |
| M2 | 照片與 OCR:上傳(含批次)、ZXing 前端掃碼、AI provider 抽象層+admin 設定、OCR 草稿確認頁、離線佇列 | 拍照→自動填表→確認入庫全通 |
| M3 | 通知:adapter 全套、LINE/Telegram 綁定流程、模板、重試/死信、對外 webhook+HMAC | 儲存後員工真的收到通知;webhook test 通過 |
| M4 | 交寄 + 報表:outbound 全流程、報表/匯出、保存期限排程、稽核查詢頁 | 01 §2.2/§4 驗收全過 |
| M5 | 打磨發布:PWA 安裝體驗、無障礙審計(對比自動測試)、i18n en、docs 全套、安全掃描、v1.0.0 | README 驗收定義全數通過 |

## 3. 無人值守開發循環(使用者要求:不間斷自動開發 + 代理審查)

主控 session(orchestrator)按此循環運作,**每個任務不超過一個功能點**,做完立即記錄,隨時可被接手:

```
LOOP:
 1. 讀 PROGRESS.md → 取下一個未完成任務 T
 2. 標記 T 為 in_progress(寫回 PROGRESS.md,含開始時間)
 3. 派「實作子代理」:輸入 = 任務描述 + 相關規格檔章節引用,要求附測試
 4. 跑測試與 linters(pytest / vitest / ruff / bandit / npm audit)
 5. 派「審查子代理」(獨立 context)做 Code Review(見 §5)
 6. 審查結果:
    - APPROVE → merge,T 標 done(含 commit hash),回 LOOP
    - REQUEST_CHANGES → 回實作代理修正,最多 3 輪;仍不過 → T 標 blocked
      並在 PROGRESS.md 記錄原因,跳下一任務(不要死循環燒 token)
 7. 每完成 5 個任務或每個里程碑結束:派「整合驗證子代理」
    跑 docker compose up + E2E smoke(Playwright),並更新 CHANGELOG
 8. Token/context 將盡時:執行 09-HANDOFF.md 交接程序後結束 session
```

穩定性守則:絕不在測試紅燈時進下一任務;絕不跳過審查;blocked 累積 ≥3 時停止並等待人類。

## 4. 子代理任務分工(可平行的組)

- A 組(後端):models+migration → services → API 端點(依 02/03)
- B 組(前端):設計 token+元件庫 → 頁面(依 06)
- C 組(整合):OCR provider(04)、通知 adapter(05)——依賴 A 組介面凍結後開工
- 平行規則:A/B 可同時;介面以 03 的 OpenAPI 為契約,前端先用 mock server(由 OpenAPI 自動生成)開發。

## 5. Code Review 協議(審查子代理的指令模板)

```
你是獨立審查者,未參與實作。輸入:diff + 對應規格檔章節。逐項檢查:
1. 規格符合:行為與 01~07 文件一致?欄位/狀態機/錯誤碼對?
2. 安全(對照 07):輸入驗證、權限檢查、加密欄位有無漏、SQL/XSS/SSRF、
   秘密是否可能進 log 或前端?
3. 測試:有無測試?測到邊界(空值、超長、權限不足、重複提交)?
4. 穩定:錯誤處理、重試、冪等、migration 可回滾?
5. 無障礙(前端):對比 token、鍵盤、aria、色彩非唯一載體?
6. 一致性:命名、i18n 文案未寫死、遵循 repo 慣例?
輸出 JSON:{ "verdict": "APPROVE"|"REQUEST_CHANGES", "blocking": [...], "suggestions": [...] }
blocking 為空才可 APPROVE。不要客氣,寧可嚴格。
```

安全敏感 diff(auth/加密/上傳/webhook)加派第二位審查者,兩者皆 APPROVE 才過。

## 6. CI(GitHub Actions)

push/PR:ruff + mypy + pytest(coverage gate 80%)+ bandit + pip-audit|eslint + vitest + npm audit|前端建置 + Lighthouse CI(a11y ≥90)+ 自動對比檢查(design tokens)|docker build + Trivy 掃描。main 分支保護:CI 綠才可 merge。

## 7. Token 預算與模型降級策略(使用者關切)

- 規劃已完成=執行不需要最強模型。建議:實作子代理用 Sonnet 級即可;審查子代理用 Opus/Fable 級(審查價值密度高);orchestrator 輕量。
- 若當前模型額度用盡:任何模型接手時只需執行 README 的「入口指令」——所有狀態都在 PROGRESS.md/DECISIONS.md,不依賴對話記憶。

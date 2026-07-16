# 09 Session 交接協議

目的:任何 session(Fable、Opus、Sonnet、其他工具)隨時可接手,不依賴前一個 session 的對話記憶。**唯一事實來源是 repo 內的檔案,不是聊天紀錄。**

## 1. 三個狀態檔(放 repo 根目錄,每次變更即 commit)

### PROGRESS.md(機器可讀的任務板)
```markdown
# PROGRESS
## 目前狀態
- 里程碑: M2
- 最後更新: 2026-07-12T14:30+08:00 by <session/model 名>
- 最後綠燈 commit: abc1234
## 任務
- [x] M2-01 上傳端點與魔數驗證 (commit def5678, reviewed: APPROVE)
- [>] M2-02 ZXing 前端掃碼元件 (started 14:10, agent: impl-B)
- [!] M2-03 HEIC 轉檔 (blocked: pillow-heif 在 alpine 編譯失敗,見 DECISIONS D-012)
- [ ] M2-04 OCR provider 抽象層
## 已知問題
- flaky test: test_notify_retry(重跑即過,待修)
```
符號:`[x]` 完成 `[>]` 進行中 `[!]` blocked `[ ]` 待辦。

### DECISIONS.md(ADR-lite,只增不改)
```markdown
## D-012 | 2026-07-12 | HEIC 支援延後到 M5
- 情境: alpine 缺 libheif,編譯失敗 3 次
- 決定: base image 改 python:3.12-slim;HEIC 先靠前端 canvas 轉 JPEG
- 理由: 不為單一格式增加 30 分鐘 build
- 影響: 07 §4 白名單暫時移除 heic
- 決策者: impl-A agent, reviewed by review agent
```
規劃檔(01~07)與 DECISIONS 衝突時,以 DECISIONS 較新者為準,並回頭在規劃檔加註。

### THOUGHTS.md(思考紀錄,使用者要求保存思考方式)
非結構化;每個 session 追加一節:嘗試過但放棄的方案與原因、懷疑但未驗證的點、給下一個 session 的提醒。這是防止「下一個模型把走過的死路再走一遍」的檔案。

## 2. Session 開始儀式(任何接手者必做,約 5 分鐘)

1. 讀 README.md(決策表)→ PROGRESS.md → DECISIONS.md 最後 10 條 → THOUGHTS.md 最後一節。
2. `docker compose up -d && pytest -q` 確認接手時是綠燈;紅燈就先修,修不了記入 PROGRESS 已知問題。
3. 在 PROGRESS.md 更新「最後更新 by <自己>」再開工。

## 3. Session 結束檢查清單(token 將盡時,預留 10% 額度執行)

- [ ] 進行中任務:能收尾就收尾;不能就回滾到綠燈狀態,任務標回 `[ ]` 並在 THOUGHTS 記下進度細節
- [ ] PROGRESS.md / DECISIONS.md / THOUGHTS.md 更新並 commit
- [ ] 測試綠燈(或已知問題清單完整)
- [ ] 未 commit 的實驗代碼:刪除或收進 `experiments/` 並註記

## 4. 跨模型注意事項

- 指令都寫在檔案裡,不假設接手者看得到本對話。
- 檔案引用一律用相對路徑;不用任何模型特有功能寫進流程。
- 若接手模型能力較弱:優先做 PROGRESS 中標 `size:S` 的任務,`size:L` 留給強模型(任務建立時就標 size)。

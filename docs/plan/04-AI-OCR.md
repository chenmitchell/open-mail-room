# 04 AI OCR 設計(BYOK)

## 1. 核心原則

1. **條碼優先,AI 補位**:前端 `@zxing/browser` 先掃 1D/QR 條碼取單號(免費、即時、比 OCR 準);AI 只負責條碼拿不到的:寄件人、收件人、承運商判斷、手寫欄位。單號若條碼已取得,AI 結果不覆蓋。
2. **API Key 只存在後端**:加密存 DB(見 07 §3),絕不下發前端;前端只看到遮罩。
3. **人工確認才入庫**:OCR 結果一律是草稿,櫃台確認後才成正式紀錄——這是準確率的最後防線,也讓低信心結果無害。

## 2. Provider 抽象層

```python
class VisionOCRProvider(Protocol):
    slug: str
    async def extract(self, image: bytes, prompt: str, model: str) -> OCRResult: ...

# 實作:OpenAIProvider(也涵蓋 OpenRouter 與任何 OpenAI-compatible:填 base_url 即可,
#       如 Groq、Together、LiteLLM、Ollama 本地模型)、AnthropicProvider、GoogleGeminiProvider
```

- 設定介面(admin UI):選 provider → 填 base_url(compatible 才需要)、API key、model 名稱、priority、月預算。
- Failover:依 priority 排序,前者連續失敗 3 次或逾時即換下一個;全掛則 job 標 failed,櫃台仍可手動填寫(系統不因 AI 掛掉而不能用)。
- 月預算:累計 `cost_estimate` 超過 `monthly_budget_usd` 即停用該 provider 並通知 admin。
- 建議預設模型(2026-07,執行時再驗證現況):OpenAI `gpt-4o-mini` 級、Anthropic `claude-haiku-4-5`、Google `gemini-flash` 級、OpenRouter 任選;本地離線可用 Ollama + Qwen-VL(免 token,精度較低)。

## 3. 抽取 Prompt(版本化,存 `prompt_version`)

System prompt 要點:
```
你是包裹/郵件標籤辨識器。從照片抽取欄位,只回傳 JSON,不要多餘文字:
{
  "tracking_no": string|null,      // 託運單號/掛號號碼,只留英數字
  "carrier_guess": string|null,    // 從下列 slug 選一: chunghwa_post, tcat, hct, kerrytj, ecan, sf, dhl, fedex, ups, seven_eleven, familymart, messenger, other
  "sender_name": string|null,
  "sender_org": string|null,
  "sender_phone": string|null,
  "recipient_name": string|null,   // 收件人姓名,去除「先生/小姐/收」等後綴
  "recipient_dept_hint": string|null, // 標籤上若寫部門
  "is_handwritten": boolean,
  "confidence": number             // 0~1 整體信心
}
看不清的欄位回 null,不要猜。台灣標籤常見繁體中文,注意直式書寫與手寫。
```

### 信件(信封)與多張照片

- 信封與包裹標籤版面不同:直式書寫、手寫多、寄件人常在背面或左上。`mail_type=letter` 時 prompt 追加:「這是台灣信封,收件人常居中直式,寄件人可能在背面或左上,可能有 14 碼掛號條碼號;平信無單號屬正常,回 null 即可」。
- 同一件多張照片:**多圖一次送同一個 vision 請求**(OpenAI/Anthropic/Google/OpenRouter 皆支援 multi-image),由模型綜合判讀——比逐張抽取後合併更準且省 token。Fallback(provider 不支援多圖時):逐張抽取,欄位合併規則=取信心最高的非空值;兩張照片同欄位值衝突時,該欄位標警示,由櫃台在確認頁裁決。`ocr_jobs` 因此允許一個 job 綁多個 attachment(`attachment_id` 改為 `attachment_ids` JSON 陣列)。
- 機密件(雙掛號/存證信函):依 07,可設定禁用 AI,僅掃條碼+手動。

後處理:`tracking_no` 對 carriers 表的 regex 驗證(不符 → 降信心並標警示);`carrier_guess` 與 regex 判斷交叉驗證;`recipient_name` 進模糊比對(01 §5)。

## 4. 成本控制

- 影像前處理:上傳原圖保留存證,送 AI 前壓縮至長邊 1280px、JPEG q80(標籤文字足夠)。
- 條碼已取得單號時,prompt 附註「單號已知,只需其他欄位」可降低輸出 token。
- 每 job 記 tokens/cost;admin 報表顯示每月 AI 花費;粗估:一張標籤約 1k~2k image tokens,以 mini/haiku 級模型計,**每千件約 US$1~3**。
- 開源使用者無 key 時:系統可用「純手動模式」+ 條碼掃描,AI 為增強而非依賴。

## 5. 隱私

送出前提示使用者:照片將傳至所選 AI 服務商;文件記載各家資料保留政策連結;支援本地 Ollama 讓照片不出內網(對機密環境重要)。機密件可設定「禁用 AI OCR,僅手動」。

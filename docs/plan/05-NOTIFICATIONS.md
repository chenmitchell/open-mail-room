# 05 通知設計

## 1. 重要前提

**LINE Notify 已於 2025/3/31 停用,不可使用。** LINE 通知一律走「LINE 官方帳號 + Messaging API」。台灣 2026 資費:輕用量方案 0 元/月、免費 200 則推播/月(Push 計費、Reply 不計費)。→ 中大型公司光靠免費額度不夠,因此本系統把 LINE 視為「其中一個 adapter」,並提供免費替代(Telegram/Email/Webhook)。

## 2. Adapter 架構

```python
class NotifyChannel(Protocol):
    slug: str
    async def send(self, binding: Binding, message: RenderedMessage) -> SendResult: ...
```

| Adapter | 說明 | 成本 |
|---|---|---|
| line | Messaging API push;需 OA channel token | 200 則/月免費,超過需付費方案 |
| telegram | Bot API;額度寬鬆 | 免費 |
| slack | Incoming Webhook 或 Bot token | 免費 |
| discord | Webhook | 免費 |
| email | SMTP(host/port/tls 設定) | 依 SMTP |
| webhook | 通用 HTTP POST(HMAC 簽章同 03 §3),讓公司串自有系統/內部 IM | 免費 |
| webpush | 瀏覽器 Web Push(PWA 加分項,v1.5) | 免費 |

員工可綁多通道;通知策略可設「全部發送」或「依優先序發第一個成功的」。

## 3. LINE 綁定流程(Messaging API 沒有「拿 email 查 userId」的能力,必須讓員工主動綁定)

1. 員工在 PWA 按「綁定 LINE」→ 系統產生 6 位綁定碼(10 分鐘有效)。
2. 員工掃 QR 加公司 LINE OA 好友,對 OA 傳送綁定碼。
3. 系統的 LINE webhook 收到訊息 → 核對綁定碼 → 存 userId 至 notification_bindings → 回覆「綁定成功」。
4. Telegram 同理(deep link `t.me/bot?start=<code>` 更簡單)。

## 4. 訊息模板(存 settings,可套版自訂,支援變數)

- `received`:「📦 您有 {mail_type} 到櫃台|寄件:{sender}|單號:{tracking_no}|請至 {pickup_location} 領取,出示取件碼 {pickup_code}」
- `reminder`(預設 2 天未領):「提醒:您的包裹已到 {days} 天,請儘速領取」
- `overdue`(7 天):同時通知員工與部門主管
- 機密件模板:不含寄件人與內容描述。
- 交寄:`outbound.shipped` 通知申請人單號。

## 5. 可靠性

- 通知走背景佇列;失敗指數退避重試 5 次 → dead 狀態進「通知失敗」清單,櫃台可見並手動處理(打分機)。
- 每則通知記錄 channel、狀態、錯誤;報表可查通知成功率。
- LINE 額度將盡(當月 >180 則)時告警 admin,並可設定自動 fallback 到 email。

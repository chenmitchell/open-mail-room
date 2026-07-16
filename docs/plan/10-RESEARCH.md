# 10 調查結果(2026-07-09)

## 1. 開源現況:有明確空缺

- 直接同類(收發室登記)只有死掉或畢設等級專案:mailroomxpress(2012 停更)、rice-apps/mailroom(校內用)、多個中國「校園驛站」畢設(pack-java、ssm016 等)。
- 鄰近但不同題:PackageMate、courier(自架「追蹤號查詢」,無收件登記/通知/簽收)、karrio(寄件向 shipping API,活躍度最高的鄰近專案,可參考其 carrier 抽象設計)。
- LLM Vision 標籤 OCR:無完整開源實作,只有積木——Roboflow + Qwen-VL pipeline(概念驗證)、getomni-ai/zerox(通用文件 OCR→JSON)、icereed/paperless-gpt(架構參考);Veryfi 商用 API 證明此路可行。
- 台灣/中文:僅閉源商用(智生活 6,500+ 社區、社區幫),零開源選項。
- 結論:**「拍標籤→AI 抽取→名錄比對→通知→簽收」的開源實作是空白**,本專案有差異化價值:self-hosted、Docker 一鍵、BYOK(含本地 Ollama)、繁中標籤支援。

## 2. 商用功能對照(規格參考來源)

Notifii Track / PackageX Mailroom / Envoy Deliveries / Parcel Tracker / EZTrackIt 的共同功能:拍照掃碼登記、OCR 抽收件人+承運商+單號、名冊模糊比對(含暱稱)、多通道通知+自動提醒、取件簽名/照片/QR 核銷、滯留件管理、報表、名錄整合(AD/HR/CSV)。→ 已全數納入 01 規格。

## 3. 台灣收發通路與單號格式(carriers 種子資料依據)

| 通路 | slug | 單號格式(regex 草案) | 備註 |
|---|---|---|---|
| 中華郵政掛號/包裹 | chunghwa_post | `^\d{14}$`(查詢系統亦收 20 碼) | 平信無單號 |
| 中華郵政快捷 EMS | chunghwa_post_ems | `^[A-Z]{2}\d{9}TW$`(國際) | 國內走郵件查詢系統 |
| 中華郵政 i郵箱 | chunghwa_post_ibox | 同包裹體系 | 取件保留 3 天 |
| 黑貓宅急便 | tcat | `^\d{12}$` | |
| 新竹物流 | hct | `^\d{10}$` | |
| 嘉里大榮 | kerrytj | `^\d{10,11}$` | 常溫 11、低溫 10 |
| 台灣宅配通 | ecan | `^\d{12}` | 查詢取前 12 碼 |
| 順豐速運 | sf | `^SF\d{12,15}$`(未官方公告,寬鬆) | |
| DHL Express | dhl | `^\d{10}$` | |
| FedEx | fedex | `^\d{12,14}$` | |
| UPS | ups | `^1Z[0-9A-Z]{16}$` | |
| 7-11 交貨便 | seven_eleven | `^G\d{10}$`(寬鬆) | |
| 全家店到店 | familymart | 未知,不設 regex | |
| 機車快遞(全球快遞/Lalamove/即刻送) | messenger | 無公開格式 | |
| 其他 | other | 無 | |

> regex 僅作「信心加分/警示」用,不得阻擋儲存(格式可能變動)。

## 4. 通知現況

- **LINE Notify 已於 2025/3/31 終止**,token 全失效。替代=LINE OA + Messaging API:2026 台灣資費輕用量 0 元/200 則推播/月(不可加購)、中用量 800 元/3,000 則、高用量 1,200 元/6,000 則;Reply 不計費、Push 計費。
- Telegram Bot / Slack / Discord webhook / Email / Web Push 免費。

## 5. 承運商 API

中華郵政有「郵件查詢網路介接」與 OPEN API 但需書面申請;黑貓/新竹/大榮/宅配通有 B2B EDI 但需契約客戶;間接可走綠界物流 API 或 TrackingMore 等聚合商(付費)。→ 因此 v1 不做自動貨態追蹤,留 plugin 介面(01 §7)。

## 6. 個資法重點(蒐集姓名/照片即適用)

- 姓名、照片屬個資法第 2 條個人資料;蒐集需履行第 8 條告知義務(目的、類別、期間、權利)。
- 第 11 條:目的消失或期限屆滿應刪除/停止利用;實務常以損害賠償時效(第 30 條,最長 5 年)訂保存 5 年。→ 系統內建保存期限自動化與告知範本(07)。
- 不得公開張貼含姓名之登記資料(傳統櫃台紙本簽收簿其實有此問題,本系統反而是改善)。

*詳細來源 URL 保存在專案 wiki 草稿;主要:GitHub 各專案頁、notifii.com、packagex.io、envoy.com、parceltracker.com、中華郵政 post.gov.tw、各物流商官網查詢頁、數位時代/經理人 LINE Notify 報導、anyong 2026 LINE OA 資費整理、全國法規資料庫個資法。*

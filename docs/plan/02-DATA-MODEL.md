# 02 資料模型

SQLAlchemy 2 declarative;Alembic 管 migration;SQLite/PostgreSQL 皆可跑(避免 DB 特有型別,JSON 欄位用 SQLAlchemy `JSON`)。所有表含 `id`(UUID v7 字串)、`created_at`、`updated_at`。敏感欄位加密方式見 07 §3。

## 表清單

### users(系統使用者:admin/counter/viewer)
`email`(唯一)、`password_hash`(argon2id)、`display_name`、`role`、`is_active`、`totp_secret`(加密,可選 2FA)、`last_login_at`

### departments
`name`、`code`(唯一)、`parent_id`(自參照,支援階層)、`manager_employee_id`、`is_active`

### employees(收件人名錄,與 users 分離——員工不一定登入)
`name`、`aliases`(JSON 陣列)、`department_id`、`ext`、`email`(加密)、`phone`(加密)、`status`(active/inactive)、`pickup_code`(隨機 8 碼,領取核銷用)、`user_id`(可選,綁登入帳號)

### notification_bindings
`employee_id`、`channel`(line/telegram/slack/discord/email/webhook/webpush)、`address`(加密:LINE userId、chatId、URL…)、`is_verified`、`verified_at`

### carriers(種子資料含台灣通路,可自行增修)
`name`、`slug`、`kind`(postal/courier/freight/store/messenger/other)、`tracking_pattern`(regex,可空)、`is_active`
> 種子:中華郵政(平信/掛號/包裹/快捷/i郵箱)、黑貓、新竹物流、嘉里大榮、台灣宅配通、順豐、DHL、FedEx、UPS、7-11 交貨便、全家店到店、機車快遞、其他。regex 參考 10-RESEARCH.md 單號格式表。

### mail_items(收件)
`item_no`(IN-YYYYMMDD-####,唯一)、`direction`(固定 inbound)、`tracking_no`(索引)、`carrier_id`、`mail_type`(letter/document/parcel/box/pallet)、`sender_name`、`sender_org`、`sender_phone`(加密)、`recipient_employee_id`、`recipient_name_raw`(OCR 原文)、`department_id`(冗餘存放,防部門改組後歷史錯亂)、`received_at`、`received_by`(user_id)、`status`(見 01 §3 狀態機)、`is_confidential`、`is_cod`、`cod_amount`、`refrigeration`(none/chilled/frozen)、`size_note`、`note`、`notified_at`、`remind_count`、`picked_up_at`、`picked_up_by_name`、`pickup_method`(signature/pickup_code/qr)、`ocr_job_id`

### outbound_items(交寄)
`item_no`(OUT-…)、`applicant_employee_id`、`department_id`、`to_name`、`to_org`、`to_address`(加密)、`to_phone`(加密)、`carrier_id`、`tracking_no`、`shipped_at`、`cost`、`payment`(company/dept_code/personal)、`status`(pending/shipped/delivered/exception)、`note`

### attachments
`owner_type`(mail_item/outbound_item/pickup)、`owner_id`、`kind`(label_photo/extra_photo/damage_photo/pickup_signature/pickup_photo)、`file_path`(儲存於加密 volume,見 07)、`sha256`、`mime`、`size_bytes`、`width`、`height`
> 簽名以 PNG 存檔,不存筆跡向量。

### ocr_jobs
`attachment_ids`(JSON 陣列,同件多張照片綁同一 job)、`provider`、`model`、`status`(queued/running/succeeded/failed)、`result_json`(結構化抽取結果)、`confidence`、`barcode_results`(JSON)、`prompt_version`、`tokens_in`、`tokens_out`、`cost_estimate`、`error`、`retries`

### notifications
`mail_item_id`、`employee_id`、`channel`、`template`(received/reminder/overdue)、`status`(queued/sent/failed/dead)、`sent_at`、`error`、`retries`

### webhook_endpoints(對外推送)
`name`、`url`、`secret`(加密,HMAC 簽章用)、`events`(JSON 陣列)、`is_active`、`last_success_at`、`failure_count`

### api_keys
`name`、`key_hash`(僅存 hash,建立時顯示一次)、`scopes`(JSON)、`expires_at`、`last_used_at`、`is_active`

### ai_provider_configs
`provider`(openai/anthropic/google/openrouter/openai_compatible)、`base_url`(compatible 用)、`api_key_encrypted`、`model`、`priority`(failover 順序)、`monthly_budget_usd`(可空,超過即停用並告警)、`is_active`

### audit_logs(僅追加,禁 UPDATE/DELETE)
`actor_type`(user/api_key/system)、`actor_id`、`action`、`target_type`、`target_id`、`diff_json`、`ip`、`user_agent`、`at`

### settings(key-value,含 branding 覆寫)
`key`(唯一)、`value_json`、`is_secret`(secret 值加密)

## 索引重點
`mail_items(tracking_no)`、`mail_items(status, received_at)`、`mail_items(recipient_employee_id, status)`、`employees(name)`、`audit_logs(target_type, target_id, at)`

## 保存期限工作
每日排程:超過 `retention_years`(預設 5)的 mail_items/outbound_items → 依設定「匿名化」(清除姓名/電話/照片,保留統計欄位)或「刪除」;動作寫 audit log。

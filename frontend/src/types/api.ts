// Shared shapes for the /api/v1 contract — see docs/plan/03-API-SPEC.md.

export interface ApiErrorBody {
  code: string
  message: string
}

export interface ApiEnvelope<T> {
  data: T | null
  error: ApiErrorBody | null
}

export interface ApiListMeta {
  total: number
  page: number
  size: number
}

export type UserRole = 'admin' | 'counter' | 'employee' | 'viewer'

export interface AuthUser {
  id: string
  // M4-02 bug fix: backend `_user_public` (app/api/v1/auth.py) serializes
  // this field as `display_name` (from the `users.display_name` column),
  // not `name` — this type previously didn't match the real response body
  // at all (see stores/auth.ts for the matching POST /auth/login fix).
  display_name: string
  email: string
  role: UserRole
  // The caller's own employees row id (backend `_user_public` resolves it
  // via employees.user_id), or null for accounts with no directory entry
  // (a counter/admin login, typically). Lets a page that needs "who am I as
  // an employee" — the outbound applicant, for one — use an exact id instead
  // of fuzzy-matching the user's own display name back against the directory
  // and hoping nobody shares their name.
  employee_id?: string | null
  // Backend `_user_public`: resolved via employees.user_id -> the linked
  // employee's department name, `None` for accounts with no directory
  // entry (e.g. counter/admin logins). Real field, not an assumption.
  department?: string | null
  // Backend `_user_public`: the linked employee's pickup_code, `None` when
  // there is no linked employee record — needed for 06 §1 「我的郵件」
  // "待領清單(取件碼大字)". Real field, not an assumption (see M3-R1
  // blocking #5 comment in app/api/v1/auth.py `_user_public`).
  pickup_code?: string | null
}

// ---------------------------------------------------------------------------
// Domain types — 02-DATA-MODEL.md / 03-API-SPEC.md. Fields not spelled out
// explicitly in 03's response examples are marked ASSUMPTION and kept
// optional so the UI degrades gracefully if the real backend omits them.
// ---------------------------------------------------------------------------

// 01 §3 狀態機(inbound)
export type MailItemStatus =
  | 'received'
  | 'notified'
  | 'picked_up'
  | 'returned'
  | 'forwarded'
  | 'unclaimed'
  | 'destroyed'
  // 登記錯了(重複登記、拍錯照、按錯送出)。與 returned 不同 —— 退回是
  // 真的有東西被送回寄件人,作廢是那件包裹從來不存在,所以報表不算它。
  // 紀錄本身保留(稽核軌跡不能有洞),但排除在統計與所有領取路徑之外。
  | 'voided'

// 02 mail_items.mail_type
export type MailType = 'letter' | 'document' | 'parcel' | 'box' | 'pallet'

// 02 mail_items.refrigeration
export type RefrigerationType = 'none' | 'chilled' | 'frozen'

// 03 §2 POST /items/{id}/pickup body.method
export type PickupMethod = 'signature' | 'pickup_code' | 'qr'

// 02 carriers.kind. ASSUMPTION: no GET /carriers endpoint is enumerated in
// 03 §2, but the carrier dropdown (06 §1 拍照登記/手動登記) needs seeded
// carrier data — see src/api/carriers.ts for the flagged assumption.
export type CarrierKind = 'postal' | 'courier' | 'freight' | 'store' | 'messenger' | 'other'

export interface Carrier {
  id: string
  name: string
  slug: string
  kind: CarrierKind
  is_active: boolean
}

export interface Department {
  id: string
  name: string
  code: string
  parent_id?: string | null
  manager_employee_id?: string | null
  is_active: boolean
}

export interface DepartmentCreatePayload {
  name: string
  code: string
  parent_id?: string | null
  manager_employee_id?: string | null
  is_active?: boolean
}

export type DepartmentUpdatePayload = Partial<DepartmentCreatePayload>

export interface Employee {
  id: string
  name: string
  aliases: string[]
  department_id: string | null
  department_name?: string | null
  ext?: string | null
  email?: string | null
  phone?: string | null
  status: 'active' | 'inactive'
  pickup_code?: string | null
  user_id?: string | null
}

export interface EmployeeCreatePayload {
  name: string
  aliases?: string[]
  department_id?: string | null
  ext?: string
  email?: string
  phone?: string
  status?: 'active' | 'inactive'
}

export type EmployeeUpdatePayload = Partial<EmployeeCreatePayload>

// 01 §5 模糊比對: 分數 >=90 自動帶入、70-90 列候選、<70 留空.
// ASSUMPTION: 03 only documents `{ employee_id, score }[]` — name/department
// are assumed present too since the UI (06: "員工比對候選 chips(分數與部門)")
// cannot render useful chips without them.
export interface EmployeeMatchCandidate {
  employee_id: string
  name: string
  department_name?: string | null
  score: number
}

export interface DepartmentMatchCandidate {
  department_id: string
  name: string
  code: string
  manager_employee_id: string | null
  manager_name?: string | null
  score: number
  tier: string
}

// ASSUMPTION: response shape for POST /employees/import is not defined in
// 03/02; this mirrors the task brief's "成功/失敗行報告" requirement.
export interface EmployeeImportError {
  row: number
  message: string
}

export interface EmployeeImportResult {
  total: number
  succeeded: number
  failed: number
  errors: EmployeeImportError[]
}

export interface MailItem {
  id: string
  item_no: string
  tracking_no?: string | null
  carrier_id?: string | null
  carrier_name?: string | null
  mail_type: MailType
  sender_name?: string | null
  sender_org?: string | null
  sender_phone?: string | null
  recipient_employee_id?: string | null
  recipient_name_raw: string
  department_id?: string | null
  department_name?: string | null
  received_at: string
  received_by?: string | null
  status: MailItemStatus
  is_confidential: boolean
  is_cod: boolean
  cod_amount?: number | null
  refrigeration: RefrigerationType
  size_note?: string | null
  note?: string | null
  notified_at?: string | null
  remind_count: number
  picked_up_at?: string | null
  picked_up_by_name?: string | null
  pickup_method?: PickupMethod | null
}

// 03 §2 POST /items body — id/item_no/status/timestamps are server-assigned.
export interface CreateMailItemPayload {
  tracking_no?: string
  carrier_id?: string
  mail_type: MailType
  sender_name?: string
  sender_org?: string
  recipient_employee_id?: string | null
  recipient_name_raw: string
  department_id?: string | null
  is_confidential?: boolean
  is_cod?: boolean
  cod_amount?: number
  refrigeration?: RefrigerationType
  size_note?: string
  note?: string
  // M2 OCR confirm flow (src/pages/inbound/OcrConfirmPage.vue#onConfirm):
  // links the created item back to the OCR job/photos it was confirmed
  // from. M2-LINK: `MailItemCreate` (backend/app/api/v1/mail_items.py) now
  // accepts both fields (previously `extra="forbid"` 422'd on them) --
  // ocr_job_id is validated against ocr_jobs and stored on the item;
  // attachment_ids must reference pending (unlinked) attachments and are
  // bound to the created item.
  ocr_job_id?: string
  attachment_ids?: string[]
}

export interface PickupPayload {
  method: PickupMethod
  picked_up_by_name: string
  signature_png_base64?: string
  pickup_code?: string
}

// 03 §2 GET /items query params + 01 §4 全欄位可搜尋.
export interface ItemsQuery {
  q?: string
  status?: MailItemStatus
  carrier_id?: string
  department_id?: string
  date_from?: string
  date_to?: string
  confidential?: boolean
  page?: number
  size?: number
}

// M1-R1 blocking #3: POST /pickup/lookup response employee sub-object --
// deliberately a *smaller* shape than `Employee` (no aliases/status/etc,
// and critically no `pickup_code` — see app/api/v1/pickup.py) since this is
// what the counter's pickup-code lookup flow gets back, not a full
// directory record.
export interface PickupLookupEmployee {
  id: string
  name: string
  department_id: string | null
  department_name?: string | null
}

export interface PickupLookupResult {
  employee: PickupLookupEmployee
  items: MailItem[]
}

// ---------------------------------------------------------------------------
// M2 上傳/OCR — 03-API-SPEC.md §2 "照片與 OCR", 04-AI-OCR.md.
// ---------------------------------------------------------------------------

// `POST /uploads` response item (app/api/v1/uploads.py `_serialize`).
export interface UploadedAttachment {
  id: string
  kind: string
  mime: string
  size_bytes: number
  width: number
  height: number
  /**
   * EXIF DateTimeOriginal, as a UTC ISO string, or null when the photo
   * carried no EXIF (screenshots, re-saved images, most PNGs). The backend
   * lifts this out before it strips the EXIF block (GPS is personal data),
   * so it is the only EXIF field that survives intake.
   */
  captured_at: string | null
  sha256: string
}

// Normalised client-side barcode scan result (src/barcode/mapResult.ts —
// wraps a raw ZXing `Result`). `format` is the ZXing `BarcodeFormat` name
// (e.g. `CODE_128`, `QR_CODE`), kept as a string so this module never has to
// import @zxing/library's types.
export interface BarcodeHint {
  value: string
  format: string
}

// `GET /ocr/jobs/{id}` (and the `POST /ocr/jobs` create response, same
// shape) — app/api/v1/ocr_jobs.py `serialize_job`. Only `id`/`attachment_ids`
// /`status` are guaranteed present at every status (see src/ocr/pollJob.ts);
// everything else is only populated once the job leaves `queued`.
export interface OcrJob {
  id: string
  attachment_ids: string[]
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  provider?: string | null
  model?: string | null
  confidence?: number | null
  prompt_version?: string | null
  tokens_in?: number | null
  tokens_out?: number | null
  cost_estimate?: number | null
  error?: string | null
  retries?: number
  created_at?: string
  updated_at?: string
}

// The `draft` sub-object of `GET /ocr/jobs/{id}/draft` — the OCR extraction
// result pre-filled for the counter-confirmation screen (04 §3's JSON
// schema, app/ocr/schema.py `OCRResult`), plus the cross-validated
// `carrier_id` and `warnings` app/ocr/pipeline.py's `result_json` adds on
// top of the raw model output.
export interface OcrDraftFields {
  tracking_no: string | null
  carrier_guess: string | null
  carrier_id?: string | null
  sender_name: string | null
  sender_org: string | null
  sender_phone: string | null
  recipient_name: string | null
  recipient_dept_hint: string | null
  is_handwritten: boolean | null
  confidence: number
  warnings?: string[]
}

// `GET /ocr/jobs/{id}/draft` (app/api/v1/ocr_jobs.py `get_ocr_job_draft`).
export interface OcrDraft {
  job_id: string
  status: string
  error?: string | null
  draft: OcrDraftFields
  employee_candidates: EmployeeMatchCandidate[]
  department_candidates?: DepartmentMatchCandidate[]
  barcode_results?: Record<string, string>
}

// ---------------------------------------------------------------------------
// M3-02 通知綁定 — 03-API-SPEC.md §2 "通知綁定(員工自助)", 05-NOTIFICATIONS.md.
// Backend (M3-01) is developed in parallel; these mirror the documented
// contract and flag every gap as ASSUMPTION per the task brief.
// ---------------------------------------------------------------------------

// 05 §2 adapter 架構表.
export type NotificationChannel =
  | 'line'
  | 'telegram'
  | 'slack'
  | 'discord'
  | 'email'
  | 'webhook'
  | 'webpush'

// 02 notification_bindings. `address` is `Encrypted` at rest (backend/app/
// models/notification_binding.py). ASSUMPTION: the API returns it masked for
// display, mirroring 03 §2 admin/ai-providers' documented "key 只寫不讀,回
// 遮罩 sk-***abc" convention — the UI never assumes it can read the raw LINE
// userId/chatId/URL back.
export interface NotificationBinding {
  id: string
  channel: NotificationChannel
  address: string
  is_verified: boolean
  verified_at?: string | null
  created_at?: string
}

// `POST /me/bindings/line/start` response (03 §2 / 05 §3 步驟 1: 6 位碼,
// 10 分鐘有效). ASSUMPTION: exact field names aren't spelled out in 03 —
// this is the natural pairing for a wizard countdown UI.
export interface BindingStartResult {
  code: string
  expires_at: string
}

// ASSUMPTION (see src/notifications/pollBinding.ts header): 05 §3 point 4
// "Telegram 同理(deep link t.me/bot?start=<code>)" implies a start endpoint
// symmetric to LINE's; 03 §2 only spells out the LINE one explicitly.
// `deep_link` is assumed server-built so the frontend never hardcodes the
// bot's @username.
export interface TelegramBindingStartResult extends BindingStartResult {
  deep_link: string
}

// `POST /me/bindings/{channel}` body for the direct-entry channels
// (email/slack/discord/webhook — 05 §2 table; line/telegram use the
// code-wizard flow above instead).
export interface CreateBindingPayload {
  address: string
}

// ASSUMPTION: 03-API-SPEC.md §2's table doesn't list `GET /me/items`
// explicitly (only `/me/bindings/*`), but the task brief pins this exact
// path and 06 §1 「我的郵件」("自己的待領/歷史") requires it. Mirrors
// `GET /items`' paginated shape, scoped server-side to the logged-in
// employee.
export interface MyItemsQuery {
  status?: MailItemStatus
  page?: number
  size?: number
}

// ---------------------------------------------------------------------------
// M3-02 通知失敗清單 — 05-NOTIFICATIONS.md §5, 02-DATA-MODEL.md `notifications`.
// ---------------------------------------------------------------------------

export type NotificationRecordStatus = 'queued' | 'sent' | 'failed' | 'dead'

// ASSUMPTION: `item_no` / `recipient_name` are denormalized read-model
// fields (not in 02's bare `notifications` column list), added so the
// 通知失敗清單 table can render something meaningful without an extra
// per-row fetch — same pattern as `MailItem.carrier_name`/`department_name`
// elsewhere in this file. `GET /notifications` itself is also an ASSUMPTION
// — see src/api/notifications.ts.
export interface NotificationRecord {
  id: string
  mail_item_id: string
  item_no?: string | null
  recipient_name?: string | null
  employee_id: string
  channel: NotificationChannel
  template: 'received' | 'reminder' | 'overdue'
  status: NotificationRecordStatus
  sent_at?: string | null
  error?: string | null
  retries: number
}

// ---------------------------------------------------------------------------
// M3-02 admin webhooks — 02 `webhook_endpoints`, 03 §2/§3.
// ---------------------------------------------------------------------------

// 03 §3 事件清單.
export const WEBHOOK_EVENTS = [
  'item.received',
  'item.notified',
  'item.reminder',
  'item.picked_up',
  'item.returned',
  'item.unclaimed',
  'outbound.shipped',
] as const
export type WebhookEvent = (typeof WEBHOOK_EVENTS)[number]

export interface WebhookEndpoint {
  id: string
  name: string
  url: string
  events: string[]
  is_active: boolean
  last_success_at?: string | null
  failure_count: number
}

export interface WebhookEndpointPayload {
  name: string
  url: string
  events: string[]
  is_active?: boolean
}

// ASSUMPTION: `POST /admin/webhooks` returning the HMAC `secret` once at
// creation time isn't spelled out in 03/02, but mirrors `api_keys`'
// documented "key_hash(僅存 hash,建立時顯示一次)" pattern — the frontend
// can't sign anything itself, so the operator needs the raw secret exactly
// once to hand to the subscriber (07 §3 HMAC signing).
export interface WebhookEndpointCreated extends WebhookEndpoint {
  secret: string
}

// `POST /admin/webhooks/{id}/test` response. ASSUMPTION: shape isn't
// specified in 03; this is the minimum the task brief's "顯示結果" needs.
export interface WebhookTestResult {
  success: boolean
  status_code?: number | null
  message?: string | null
  sent_at: string
}

// ---------------------------------------------------------------------------
// M4-02 交寄(outbound) — 01-REQUIREMENTS.md §2.2/§3 「交寄欄位」,
// 03-API-SPEC.md §2 「交寄」, backend/app/models/outbound_item.py +
// app/models/enums.py (M4-01, developed in parallel — mirrored exactly,
// not an assumption): `OutboundStatus` = pending|shipped|delivered|
// exception, `OutboundPayment` = company|dept_code|personal.
// ---------------------------------------------------------------------------

export type OutboundStatus = 'pending' | 'shipped' | 'delivered' | 'exception'
export type OutboundPayment = 'company' | 'dept_code' | 'personal'

export interface OutboundItem {
  id: string
  item_no: string
  applicant_employee_id?: string | null
  // Denormalized display fields, same convention as
  // `MailItem.department_name`/`carrier_name`. M4-R1: these were an
  // ASSUMPTION written before the backend landed, and the backend never
  // actually sent them — so the list rendered 「—」 in all three columns
  // regardless of the data. `serialize_outbound_item` now resolves them
  // (via a join in the list endpoint), so the contract is real.
  applicant_name?: string | null
  department_id?: string | null
  department_name?: string | null
  to_name?: string | null
  to_org?: string | null
  to_address?: string | null
  to_phone?: string | null
  carrier_id?: string | null
  carrier_name?: string | null
  tracking_no?: string | null
  shipped_at?: string | null
  cost?: number | null
  payment?: OutboundPayment | null
  status: OutboundStatus
  note?: string | null
  created_at?: string
}

// 03 §2 `POST /outbound` — id/item_no/status/shipped_at are server-assigned.
export interface CreateOutboundPayload {
  applicant_employee_id?: string | null
  department_id?: string | null
  to_name?: string
  to_org?: string
  to_address?: string
  to_phone?: string
  carrier_id?: string
  payment?: OutboundPayment
  cost?: number
  note?: string
}

export type UpdateOutboundPayload = Partial<CreateOutboundPayload>

// ASSUMPTION: 03 only lists bare `GET /outbound` with no documented query
// params. Mirrors `ItemsQuery`'s documented filter convention (01 §4 「全
// 欄位可搜尋」applies to outbound too — 交寄清單「篩選狀態」per the task
// brief is the one filter guaranteed needed).
export interface OutboundQuery {
  q?: string
  status?: OutboundStatus
  department_id?: string
  carrier_id?: string
  date_from?: string
  date_to?: string
  page?: number
  size?: number
}

// 03 §2 `POST /outbound/{id}/shipped { tracking_no?, attachment_id? }`.
export interface MarkShippedPayload {
  tracking_no?: string
  attachment_id?: string
}

// ---------------------------------------------------------------------------
// M4-02 報表 — 03-API-SPEC.md §2 `GET /reports/summary?from=&to=&group_by=
// department|carrier|day`, 01-REQUIREMENTS.md §4 「報表:每日/每月件量、各
// 部門件量、平均領取時間、滯留清單、各承運商佔比」.
// ASSUMPTION (flag for backend/reviewer, M4-01 developed in parallel): 03
// does not spell out the response body shape for this endpoint at all
// (unlike most others which at least show a payload example) — the shape
// below is inferred from the query params + 01 §4's list of report metrics,
// grouped into one row per bucket (department/carrier/day) plus a totals
// summary so the reports page can render stat cards without a second
// request. Confirm with backend once M4-01 lands.
// ---------------------------------------------------------------------------

export type ReportGroupBy = 'department' | 'carrier' | 'day'

export interface ReportSummaryQuery {
  from: string
  to: string
  group_by: ReportGroupBy
}

export interface ReportSummaryRow {
  /** department_id / carrier_id / ISO date, depending on group_by. */
  key: string
  /** Display label already resolved server-side (name or formatted date). */
  label: string
  received_count: number
  picked_up_count: number
  unclaimed_count: number
  /** Average time from received_at to picked_up_at, in hours. */
  avg_pickup_hours?: number | null
  /** RC-FIX #7: outbound (交寄) volume alongside the inbound metrics --
   * app/api/v1/reports.py already returns this on every row/totals. */
  outbound_shipped_count: number
}

export interface ReportSummaryTotals {
  received_count: number
  picked_up_count: number
  unclaimed_count: number
  avg_pickup_hours?: number | null
  outbound_shipped_count: number
}

export interface ReportSummary {
  group_by: ReportGroupBy
  from: string
  to: string
  rows: ReportSummaryRow[]
  totals: ReportSummaryTotals
}

// ---------------------------------------------------------------------------
// M4-02 稽核頁 — 03-API-SPEC.md §2 `GET /admin/audit-logs`,
// backend/app/models/audit_log.py (M4-01, mirrored exactly — table is
// append-only, columns below match the ORM model 1:1).
// ---------------------------------------------------------------------------

export type AuditActorType = 'user' | 'api_key' | 'system'

export interface AuditLogEntry {
  id: string
  actor_type: AuditActorType
  actor_id?: string | null
  // Resolved at read time by the backend (users.display_name, or an API
  // key's name) — `audit_logs` itself only stores actor_id, deliberately:
  // it is append-only, and a denormalized name would freeze a name that can
  // legitimately change. Null for `system` actors, which have no id.
  actor_name?: string | null
  action: string
  target_type: string
  target_id?: string | null
  diff_json?: Record<string, unknown> | null
  ip?: string | null
  user_agent?: string | null
  at: string
}

// ASSUMPTION: 03 doesn't document query params for `GET /admin/audit-logs`;
// mirrors the filter fields the append-only audit_logs schema actually has
// (target_type/target_id/actor_id/action) plus the date-range + pagination
// convention used by every other list endpoint in this file.
export interface AuditLogsQuery {
  actor_id?: string
  target_type?: string
  target_id?: string
  action?: string
  date_from?: string
  date_to?: string
  page?: number
  size?: number
}

// ---------------------------------------------------------------------------
// M7-FE admin 使用者管理 — backend contract (already live):
// `GET/POST /admin/users`, `PATCH /admin/users/{id}`,
// `POST /admin/users/{id}/reset-password`, `POST /me/password`.
// ---------------------------------------------------------------------------

/** Alias for readability at call sites talking about "user accounts and
 * their roles" specifically — same four-value RBAC set as `AuthUser.role`. */
export type Role = UserRole

// `_user_public`-shaped admin user record — deliberately has no password
// field (backend never returns one).
export interface AdminUser {
  id: string
  email: string
  display_name: string
  role: Role
  is_active: boolean
  last_login_at?: string | null
  employee_id?: string | null
  employee_name?: string | null
  created_at: string
  updated_at: string
}

// `POST /admin/users` body. `email` is immutable after creation (no update
// payload field for it — see `AdminUserUpdatePayload`).
export interface AdminUserCreatePayload {
  email: string
  display_name: string
  role: Role
  password: string
  employee_id?: string
}

// `PATCH /admin/users/{id}` body — every field optional (partial update).
// Backend rejects demoting/deactivating the last active admin with
// `LAST_ADMIN` (400).
export interface AdminUserUpdatePayload {
  display_name?: string
  role?: Role
  is_active?: boolean
  employee_id?: string | null
}

export interface AdminUsersQuery {
  page?: number
  size?: number
  q?: string
  role?: Role
  is_active?: boolean
}

// `POST /admin/users/{id}/reset-password` body.
export interface ResetPasswordPayload {
  new_password: string
}

// `POST /me/password` body — self-service change, requires the current
// password (`CURRENT_PASSWORD_INVALID` 400 on mismatch).
export interface ChangeMyPasswordPayload {
  current_password: string
  new_password: string
}

// ---------------------------------------------------------------------------
// M9-FE admin AI settings — `GET /admin/ai/status`, `GET /admin/ai/models`,
// `PUT /admin/ai/settings`. Backend contract is already live (task brief);
// this mirrors it 1:1, no ASSUMPTION markers needed here.
// ---------------------------------------------------------------------------

export interface AiStatus {
  env_key_present: boolean
  provider: string
  // "" means no DB override is set — the backend auto-detects a model.
  effective_model: string
  daily_request_limit: number
  used_today: number
  has_db_config: boolean
}

export interface AiModelsResult {
  models: string[]
}

// `PUT /admin/ai/settings` body. `model: null` (or "") clears the DB
// override back to auto-detect; omitted fields are left unchanged
// server-side.
export interface AiSettingsPayload {
  model?: string | null
  daily_request_limit?: number
}

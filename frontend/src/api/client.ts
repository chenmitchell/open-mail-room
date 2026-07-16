import type { ApiEnvelope, ApiErrorBody, ApiListMeta } from '@/types/api'

// 03-API-SPEC.md §0: all endpoints are under /api/v1; dev proxy forwards /api -> :8000.
const API_BASE = '/api/v1'

// ASSUMPTION (flag for backend team, see 07-SECURITY.md §2 "CSRF token double
// submit"): exact cookie/header names are not pinned down in 03/07. Using the
// common double-submit convention below; align with backend once it lands.
const CSRF_COOKIE_NAME = 'csrf_token'
const CSRF_HEADER_NAME = 'X-CSRF-Token'

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/**
 * Registered once (from main.ts, after pinia + router exist) so this module
 * never has to import the router/store directly — avoids a
 * client.ts <-> router <-> auth-store circular dependency.
 */
let unauthorizedHandler: (() => void) | null = null

export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler
}

function getCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  if (!match) return null
  return decodeURIComponent(match.slice(name.length + 1))
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /**
   * Skip the global 401 -> "redirect to login" side effect. Use this for the
   * login call itself (a wrong password is a 401 but is not a "session
   * expired" event, and we're already on the login page).
   */
  skipAuthRedirect?: boolean
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

// 03 §0: paginated list endpoints add a `meta: { total, page, size }` field
// alongside the standard `{ data, error }` envelope.
interface ApiListEnvelope<T> extends ApiEnvelope<T> {
  meta?: ApiListMeta
}

async function requestEnvelope<T>(
  path: string,
  options: ApiRequestOptions,
): Promise<{ envelope: ApiListEnvelope<T> | null; response: Response }> {
  const { body, skipAuthRedirect, headers, ...rest } = options

  const finalHeaders = new Headers(headers)
  const method = (rest.method ?? 'GET').toUpperCase()
  let finalBody: BodyInit | undefined

  if (body !== undefined) {
    if (body instanceof FormData) {
      // Let the browser set the multipart boundary itself (03 §2 `POST
      // /uploads` / `POST /employees/import` are multipart).
      finalBody = body
    } else {
      finalHeaders.set('Content-Type', 'application/json')
      finalBody = JSON.stringify(body)
    }
  }

  if (!SAFE_METHODS.has(method)) {
    const csrfToken = getCookie(CSRF_COOKIE_NAME)
    if (csrfToken) {
      finalHeaders.set(CSRF_HEADER_NAME, csrfToken)
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    method,
    credentials: 'include', // send the HttpOnly session cookie (03 §1)
    headers: finalHeaders,
    body: finalBody,
  })

  if (response.status === 401 && !skipAuthRedirect) {
    unauthorizedHandler?.()
  }

  if (response.status === 204) {
    return { envelope: null, response }
  }

  let envelope: ApiListEnvelope<T> | null = null
  try {
    envelope = (await response.json()) as ApiListEnvelope<T>
  } catch {
    // No/invalid JSON body — fall through to the generic error below.
  }

  if (!response.ok || envelope?.error) {
    const err: ApiErrorBody = envelope?.error ?? {
      code: 'UNKNOWN_ERROR',
      message: response.statusText || '發生未知錯誤',
    }
    throw new ApiError(err.code, err.message, response.status)
  }

  return { envelope, response }
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { envelope } = await requestEnvelope<T>(path, options)
  return (envelope?.data as T) ?? (null as T)
}

export interface ListResult<T> {
  items: T[]
  meta: ApiListMeta
}

async function requestList<T>(path: string, options: ApiRequestOptions = {}): Promise<ListResult<T>> {
  const { envelope } = await requestEnvelope<T[]>(path, options)
  const items = (envelope?.data as T[]) ?? []
  const meta = envelope?.meta ?? { total: items.length, page: 1, size: items.length || 1 }
  return { items, meta }
}

export const apiClient = {
  get: <T>(path: string, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  // Use for any endpoint documented in 03 as returning a paginated list
  // (`meta: { total, page, size }`), e.g. GET /items, GET /employees.
  getList: <T>(path: string, options?: ApiRequestOptions) =>
    requestList<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  // M9-FE `PUT /admin/ai/settings` (03-API-SPEC.md admin/ai): full-replace
  // semantics on the writable subset of fields (model / daily_request_limit).
  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}

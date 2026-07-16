// M1-R1 blocking #3: dedicated pickup-code lookup endpoint. Replaces the old
// PickupPage.vue "code" mode, which called `GET /employees?q=<code>` and
// then compared `pickup_code` client-side -- that never actually worked
// (the `q` param only ever searched `name`), and `pickup_code` is no longer
// even present in `GET /employees` responses (see app/api/v1/employees.py
// `_serialize`). The backend does the real, constant-time comparison here.
import { apiClient } from './client'
import type { PickupLookupResult } from '@/types/api'

export function lookupByPickupCode(pickupCode: string): Promise<PickupLookupResult> {
  return apiClient.post<PickupLookupResult>('/pickup/lookup', { pickup_code: pickupCode })
}

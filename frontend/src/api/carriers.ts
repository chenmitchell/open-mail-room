// M1-R1 blocking #6: GET /carriers now exists (app/api/v1/carriers.py),
// same list-with-meta shape as the sibling `GET /departments` endpoint this
// was originally modelled after on the assumption it would land that way.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type { Carrier } from '@/types/api'

export function listCarriers(query: { q?: string } = {}): Promise<ListResult<Carrier>> {
  return apiClient.getList<Carrier>(`/carriers${toQueryString(query)}`)
}

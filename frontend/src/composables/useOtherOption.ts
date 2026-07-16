// UX-VISUAL task B: shared "選其他 -> 展開必填輸入" detection logic for the
// carrier / mail_type / payment dropdowns (InboundRegisterPage.vue,
// OutboundPage.vue). Carrier options loaded from GET /carriers carry a real
// `slug` (backend/scripts/seed.py seeds slug='other', name='其他'), so slug
// is checked first; mail_type/payment are fixed literal enums with no
// backend slug today, so a literal value/label match is also accepted for
// forward-compatibility if either list ever grows an "other" entry.
export interface OtherOptionCandidate {
  value: string
  label?: string
  slug?: string
}

export function isOtherSelected(value: string, options: OtherOptionCandidate[]): boolean {
  if (!value) return false
  const opt = options.find((o) => o.value === value)
  if (!opt) return false
  return opt.slug === 'other' || opt.value === 'other' || opt.label === '其他' || opt.label === 'Other'
}

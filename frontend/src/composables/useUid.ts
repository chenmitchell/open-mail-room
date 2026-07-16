// Small, dependency-free unique-id generator for wiring up aria-* attributes
// (label/for, aria-describedby, aria-labelledby). Deliberately not using the
// Vue 3.5+ `useId()` API so this works across the whole 3.x range.
let counter = 0

export function useUid(prefix = 'oi'): string {
  counter += 1
  return `${prefix}-${counter}`
}

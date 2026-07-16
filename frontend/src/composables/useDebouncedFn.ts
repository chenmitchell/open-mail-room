// Minimal debounce helper for the "即時呼叫 /employees/match" input (01 §2.1
// step 4 / 06 §1 手動登記頁) so every keystroke doesn't fire a network call.
export function useDebouncedFn<Args extends unknown[]>(
  fn: (...args: Args) => void,
  delayMs = 300,
): (...args: Args) => void {
  let timer: ReturnType<typeof setTimeout> | undefined
  return (...args: Args) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delayMs)
  }
}

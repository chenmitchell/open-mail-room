import type { EmployeeMatchCandidate } from '@/types/api'

/** 01 §5 的高信心門檻:>= 90 才可能自動帶入,70-90 只列候選。 */
export const AUTO_FILL_SCORE = 90
export const CANDIDATE_SCORE = 70

/**
 * 從模糊比對結果挑出「可以安全自動帶入」的那一位。
 *
 * 01 §5 寫的是「score >= 90 帶入(**單一最佳**,直接選取)」——關鍵在「單一」。
 * 原本的實作是把候選依分數排序後直接取 `[0]`,只要它 >= 90 就代入。問題是台灣
 * 公司同名同姓很常見:兩位「陳怡君」都會拿到 100 分,而排序在同分時只是維持
 * SQL 回來的原始列順序,等於用資料庫的列順序決定信件算誰的。使用者不會看到任何
 * 異狀——欄位就這樣填好了——所以錯了也沒人知道:收件件會通知錯的人(別人的信件
 * 內容外洩),交寄單會掛在錯的人名下。
 *
 * 所以這裡的規則是:**只有在恰好一位達到高信心門檻時才自動帶入**。有兩位以上時
 * 不猜,把候選 chips 留給人選。多按一下的成本,遠低於一封信送錯人。
 */
export function unambiguousBestMatch(
  candidates: EmployeeMatchCandidate[],
): EmployeeMatchCandidate | null {
  const strong = candidates.filter((c) => c.score >= AUTO_FILL_SCORE)
  // 0 位 = 沒人夠像;2 位以上 = 有歧義,兩者都不該由程式決定。
  if (strong.length !== 1) return null
  return strong[0]
}

/** 依分數由高到低排序的候選(>= 70),供 chips 顯示。 */
export function rankedCandidates(
  candidates: EmployeeMatchCandidate[],
): EmployeeMatchCandidate[] {
  return candidates
    .filter((c) => c.score >= CANDIDATE_SCORE)
    .sort((a, b) => b.score - a.score)
}

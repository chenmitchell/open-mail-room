import { describe, expect, it } from 'vitest'
import { rankedCandidates, unambiguousBestMatch } from '@/pages/matchAutoFill'
import type { EmployeeMatchCandidate } from '@/types/api'

const c = (employee_id: string, name: string, score: number): EmployeeMatchCandidate => ({
  employee_id,
  name,
  score,
})

describe('unambiguousBestMatch', () => {
  it('帶入唯一一位高信心候選', () => {
    const best = unambiguousBestMatch([c('e1', '王小明', 100), c('e2', '王大明', 72)])
    expect(best?.employee_id).toBe('e1')
  })

  it('同名同姓兩位都滿分時不猜 —— 這正是它存在的理由', () => {
    // 兩位「陳怡君」都 100 分。舊版取排序後的 [0],同分時等於用 SQL 列順序
    // 決定信件算誰的,而且畫面上看不出來出過錯。
    expect(unambiguousBestMatch([c('e1', '陳怡君', 100), c('e2', '陳怡君', 100)])).toBeNull()
  })

  it('兩位都跨過門檻但分數不同時仍不猜', () => {
    // 92 分那位是不同人,只是名字很像。差 8 分不足以代替人來決定。
    expect(unambiguousBestMatch([c('e1', '林志明', 100), c('e2', '林志銘', 92)])).toBeNull()
  })

  it('最高分未達門檻時不帶入', () => {
    expect(unambiguousBestMatch([c('e1', '王小明', 89), c('e2', '王大明', 75)])).toBeNull()
  })

  it('沒有候選時回 null', () => {
    expect(unambiguousBestMatch([])).toBeNull()
  })

  it('門檻是包含 90 的', () => {
    expect(unambiguousBestMatch([c('e1', '王小明', 90)])?.employee_id).toBe('e1')
  })
})

describe('rankedCandidates', () => {
  it('濾掉 70 分以下並由高到低排序', () => {
    const ranked = rankedCandidates([c('e1', 'A', 72), c('e2', 'B', 95), c('e3', 'C', 40)])
    expect(ranked.map((r) => r.employee_id)).toEqual(['e2', 'e1'])
  })

  it('不改動傳入的陣列', () => {
    const input = [c('e1', 'A', 72), c('e2', 'B', 95)]
    rankedCandidates(input)
    expect(input.map((r) => r.employee_id)).toEqual(['e1', 'e2'])
  })

  it('70 分是包含的', () => {
    expect(rankedCandidates([c('e1', 'A', 70)])).toHaveLength(1)
  })
})

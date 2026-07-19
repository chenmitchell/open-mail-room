import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AuthorCredit from '@/components/AuthorCredit.vue'

/**
 * The attribution credit is a licence term (AGPL-3.0 + the NOTICE Section 7(b)
 * attribution requirement), not decoration. These tests make removing it a
 * failing build rather than a silent edit — so a well-meaning refactor can't
 * quietly drop the one thing the licence asks in return.
 */
describe('AuthorCredit', () => {
  it('names the original author', () => {
    const w = mount(AuthorCredit)
    expect(w.text()).toContain('Mitchell Chen')
  })

  it('links back to the author and the upstream repo', () => {
    const w = mount(AuthorCredit)
    const hrefs = w.findAll('a').map((a) => a.attributes('href'))
    expect(hrefs).toContain('https://github.com/chenmitchell')
    expect(hrefs).toContain('https://github.com/chenmitchell/open-mail-room')
  })

  it('opens external links safely', () => {
    const w = mount(AuthorCredit)
    for (const a of w.findAll('a')) {
      expect(a.attributes('rel')).toContain('noopener')
    }
  })
})

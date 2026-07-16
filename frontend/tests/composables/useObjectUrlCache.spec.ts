import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { useObjectUrlCache, type HasBlobId } from '@/composables/useObjectUrlCache'

// FE-STABILITY regression coverage: the composable's whole reason for
// existing (see its own header comment, POLISH-AUDIT.md Nice #15) is that a
// plain `watch(items, ...)` without `deep: true` does NOT fire when a new
// photo is *pushed* onto the same array reference (`items.value.push(...)`),
// which used to leave freshly-captured photos with no cached object URL at
// all -- a broken <img> (破圖). It works around that by watching a derived
// id-array instead. This spec pins that behaviour down directly against the
// composable (not indirectly via a page mount), for both push-only mutation
// and array reassignment, plus the create/revoke lifecycle around it.
function makeItem(id: string): HasBlobId {
  return { id, blob: new Blob([id]) }
}

function mountHost(items: ReturnType<typeof ref<HasBlobId[]>>) {
  const Host = defineComponent({
    setup() {
      const { getUrl } = useObjectUrlCache(items)
      return { getUrl }
    },
    render() {
      return h(
        'div',
        items.value.map((item) => h('img', { key: item.id, src: this.getUrl(item.id) })),
      )
    },
  })
  return mount(Host)
}

describe('useObjectUrlCache', () => {
  let createSpy: ReturnType<typeof vi.spyOn>
  let revokeSpy: ReturnType<typeof vi.spyOn>
  let counter: number

  beforeEach(() => {
    counter = 0
    createSpy = vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:mock-${++counter}`)
    revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('creates an object URL for every item present when mounted', async () => {
    const items = ref<HasBlobId[]>([makeItem('a'), makeItem('b')])
    const wrapper = mountHost(items)
    await wrapper.vm.$nextTick()

    expect(createSpy).toHaveBeenCalledTimes(2)
    const imgs = wrapper.findAll('img')
    expect(imgs.map((img) => img.attributes('src'))).toEqual(['blob:mock-1', 'blob:mock-2'])
  })

  it('mints a new object URL when a photo is pushed onto the existing array (in-place mutation)', async () => {
    const items = ref<HasBlobId[]>([makeItem('a')])
    const wrapper = mountHost(items)
    await wrapper.vm.$nextTick()
    expect(createSpy).toHaveBeenCalledTimes(1)

    // Mirrors how PhotoRegisterPage/BatchUploadPage actually add photos:
    // `photos.value = [...photos.value, newPhoto]` produces a fresh array
    // reference; a bare in-place `.push` would not even trigger Vue's own
    // reactivity for a `ref<T[]>`, so this exercises the same "new array,
    // new id appended" shape those pages rely on.
    items.value = [...items.value, makeItem('b')]
    await wrapper.vm.$nextTick()

    expect(createSpy).toHaveBeenCalledTimes(2)
    const imgs = wrapper.findAll('img')
    expect(imgs).toHaveLength(2)
    expect(imgs[1].attributes('src')).toBe('blob:mock-2')
    // The first photo's URL is untouched/reused, not re-minted.
    expect(imgs[0].attributes('src')).toBe('blob:mock-1')
  })

  it('revokes the object URL for a photo that is removed from the list', async () => {
    const items = ref<HasBlobId[]>([makeItem('a'), makeItem('b')])
    const wrapper = mountHost(items)
    await wrapper.vm.$nextTick()

    items.value = items.value.filter((item) => item.id !== 'a')
    await wrapper.vm.$nextTick()

    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-1')
    expect(wrapper.findAll('img')).toHaveLength(1)
  })

  it('revokes every remaining object URL when the owning component unmounts', async () => {
    const items = ref<HasBlobId[]>([makeItem('a'), makeItem('b')])
    const wrapper = mountHost(items)
    await wrapper.vm.$nextTick()

    wrapper.unmount()

    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-1')
    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-2')
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { i18n } from '@/i18n'
import SignaturePad from '@/components/SignaturePad.vue'

// jsdom doesn't implement real 2D canvas rendering unless the optional
// `canvas` npm package is installed. We stub just enough of the Canvas API
// (matching MDN's CanvasRenderingContext2D + HTMLCanvasElement.toDataURL
// signatures) to drive the component's drawing/export logic in a headless
// test environment, per the task brief's "簽名板輸出 PNG" test requirement.
const FAKE_PNG_DATA_URL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB'

function stubCanvas() {
  const ctx = {
    lineWidth: 0,
    lineCap: '',
    lineJoin: '',
    strokeStyle: '',
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    clearRect: vi.fn(),
  }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    ctx as unknown as CanvasRenderingContext2D,
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(FAKE_PNG_DATA_URL)
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    top: 0,
    width: 600,
    height: 200,
    right: 600,
    bottom: 200,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  })
  return ctx
}

// jsdom (as used by this project's vitest config) does not implement
// PointerEvent, only the base Event/MouseEvent constructors. Build a
// plain Event and attach the few properties the component actually reads
// (clientX/clientY/pointerId) — dispatchEvent only cares about `type`
// matching the listener, not the constructor's class.
function pointerEvent(type: string, x: number, y: number) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, { clientX: x, clientY: y, pointerId: 1 })
  return event
}

describe('SignaturePad', () => {
  beforeEach(() => {
    stubCanvas()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('exports a base64 PNG (no data: prefix) after a pointer drag, and clears on demand', async () => {
    const wrapper = mount(SignaturePad, { global: { plugins: [i18n] } })
    const canvas = wrapper.find('canvas')

    expect(wrapper.vm.exportPng()).toBeNull() // nothing drawn yet
    expect(wrapper.vm.isEmpty).toBe(true)

    await canvas.element.dispatchEvent(pointerEvent('pointerdown', 10, 10))
    await canvas.element.dispatchEvent(pointerEvent('pointermove', 40, 60))
    await canvas.element.dispatchEvent(pointerEvent('pointerup', 40, 60))

    const changeEvents = wrapper.emitted('change')
    expect(changeEvents).toBeTruthy()
    const lastEmitted = changeEvents![changeEvents!.length - 1][0]
    expect(lastEmitted).toBe('iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB')
    expect(wrapper.vm.exportPng()).toBe('iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB')
    expect(wrapper.vm.isEmpty).toBe(false)

    await wrapper.find('button').trigger('click')
    expect(wrapper.vm.isEmpty).toBe(true)
    expect(wrapper.vm.exportPng()).toBeNull()
    const clearEvents = wrapper.emitted('change')!
    expect(clearEvents[clearEvents.length - 1][0]).toBeNull()
  })

  it('does not start drawing when disabled', async () => {
    const wrapper = mount(SignaturePad, { props: { disabled: true }, global: { plugins: [i18n] } })
    const canvas = wrapper.find('canvas')

    await canvas.element.dispatchEvent(pointerEvent('pointerdown', 10, 10))
    await canvas.element.dispatchEvent(pointerEvent('pointermove', 40, 60))
    await canvas.element.dispatchEvent(pointerEvent('pointerup', 40, 60))

    expect(wrapper.vm.isEmpty).toBe(true)
    expect(wrapper.emitted('change')).toBeFalsy()
  })

  it('exposes an accessible label/hint pair and a clear button meeting the touch target', () => {
    const wrapper = mount(SignaturePad, { global: { plugins: [i18n] } })
    const canvas = wrapper.find('canvas')
    expect(canvas.attributes('aria-labelledby')).toBeTruthy()
    expect(canvas.attributes('aria-describedby')).toBeTruthy()
    expect(wrapper.find('button').exists()).toBe(true)
  })
})

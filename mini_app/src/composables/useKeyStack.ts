import { computed, nextTick, onScopeDispose, ref } from 'vue'
import type { ComponentPublicInstance, Ref } from 'vue'
import type { VpnKey } from '../types'
import { useReducedMotion } from './useReducedMotion'

interface Gesture { id: number; x: number; y: number; at: number; delta: number; horizontal: number; dragging: boolean }
export function useKeyStack(keys: Ref<readonly VpnKey[]>, selectedId: Ref<string | null>) {
  const stage = ref<HTMLElement | null>(null)
  const isDragging = ref(false)
  const announcement = ref('')
  const reduced = useReducedMotion()
  const cardElements = new Map<string, HTMLElement>()
  const animations = new Set<Animation>()
  const selectedIndex = computed(() => Math.max(0, keys.value.findIndex(key => key.id === selectedId.value)))
  const depth = (index: number) => keys.value.length ? (index - selectedIndex.value + keys.value.length) % keys.value.length : 0
  let busyUntil = 0
  let gesture: Gesture | null = null
  let wheelSum = 0
  let lastWheel = 0
  const setCardRef = (id: string, node: Element | ComponentPublicInstance | null) => {
    if (node instanceof HTMLElement) cardElements.set(id, node); else cardElements.delete(id)
  }
  function animate(element: HTMLElement, frames: Keyframe[], options: KeyframeAnimationOptions, done?: () => void) {
    if (reduced.value || !element.animate) { done?.(); return }
    const animation = element.animate(frames, options)
    animations.add(animation)
    animation.finished.then(() => { animations.delete(animation); done?.() }, () => animations.delete(animation))
  }
  function resetTransforms() { for (const card of cardElements.values()) { card.style.removeProperty('transform'); card.style.removeProperty('opacity') } }
  function settle() {
    for (const card of cardElements.values()) {
      const from = { transform: getComputedStyle(card).transform, opacity: getComputedStyle(card).opacity }
      card.style.removeProperty('transform'); card.style.removeProperty('opacity')
      animate(card, [from, { transform: getComputedStyle(card).transform, opacity: getComputedStyle(card).opacity }], { duration: 240, easing: 'cubic-bezier(.22,1,.36,1)' })
    }
  }
  async function select(index: number): Promise<boolean> {
    index = Math.max(0, Math.min(keys.value.length - 1, index))
    const target = keys.value[index]
    if (!target || index === selectedIndex.value || performance.now() < busyUntil || !Number.isInteger(index)) return false
    const previous = selectedIndex.value
    const outgoing = cardElements.get(keys.value[previous]?.id ?? '')
    const frames = new Map([...cardElements].map(([id, card]) => [id, { transform: getComputedStyle(card).transform, opacity: getComputedStyle(card).opacity }]))
    busyUntil = performance.now() + (reduced.value ? 0 : 440)
    outgoing?.classList.add('is-departing')
    if (outgoing) outgoing.style.zIndex = '5'
    resetTransforms()
    selectedId.value = target.id
    await nextTick()
    const direction = index > previous ? -1 : 1
    for (const [id, card] of cardElements) {
      const from = frames.get(id)
      if (!from) continue
      if (card === outgoing) {
        animate(card, [from, { transform: `translate3d(0,${direction * 75}px,0) scale(.975) rotateX(${direction * -5}deg)`, opacity: 0 }], { duration: 325, easing: 'cubic-bezier(.3,0,.2,1)' }, () => { card.classList.remove('is-departing'); card.style.removeProperty('z-index') })
      } else animate(card, [from, { transform: getComputedStyle(card).transform, opacity: getComputedStyle(card).opacity }], { duration: 440, easing: 'cubic-bezier(.22,1,.36,1)' })
    }
    const inner = cardElements.get(target.id)?.querySelector<HTMLElement>('.snapshot-card-content')
    if (inner) animate(inner, [{ opacity: .3, transform: 'translateY(5px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 300, easing: 'ease-out' })
    announcement.value = `Key ${index + 1} of ${keys.value.length}: ${target.plan} · ${target.location}`
    return true
  }
  function onPointerDown(event: PointerEvent) {
    if (!event.isPrimary || event.button !== 0 || (event.target instanceof Element && event.target.closest('button,input,a')) || performance.now() < busyUntil || keys.value.length < 2) return
    gesture = { id: event.pointerId, x: event.clientX, y: event.clientY, at: performance.now(), delta: 0, horizontal: 0, dragging: false }
    stage.value?.setPointerCapture(event.pointerId)
  }
  function onPointerMove(event: PointerEvent) {
    if (!gesture || gesture.id !== event.pointerId) return
    gesture.delta = event.clientY - gesture.y; gesture.horizontal = event.clientX - gesture.x
    if (Math.abs(gesture.delta) < 5 || Math.abs(gesture.delta) < Math.abs(gesture.horizontal) * 1.15) return
    gesture.dragging = true; isDragging.value = true
    const canMove = gesture.delta < 0 ? selectedIndex.value < keys.value.length - 1 : selectedIndex.value > 0
    const dy = Math.max(-85, Math.min(85, gesture.delta * (canMove ? .6 : .16)))
    const progress = Math.min(1, Math.abs(gesture.delta) / 150)
    keys.value.forEach((key, index) => {
      const card = cardElements.get(key.id); if (!card) return
      const d = depth(index)
      if (d === 0) card.style.transform = `translate3d(0,${dy}px,0) scale(${1 - progress * .018}) rotateX(${-dy * .035}deg)`
      else if (d < 3 && canMove) card.style.transform = `translateY(${d * 11 - progress * 5}px) scale(${1 - d * .045 + progress * .018})`
    })
  }
  async function onPointerUp(event: PointerEvent) {
    if (!gesture || gesture.id !== event.pointerId) return
    const swipe = gesture; gesture = null; isDragging.value = false
    if (stage.value?.hasPointerCapture(event.pointerId)) stage.value.releasePointerCapture(event.pointerId)
    const elapsed = Math.max(1, performance.now() - swipe.at)
    const valid = event.type !== 'pointercancel' && swipe.dragging && Math.abs(swipe.delta) > Math.abs(swipe.horizontal) * 1.15 && (Math.abs(swipe.delta) > 34 || Math.abs(swipe.delta) > 14 && Math.abs(swipe.delta) / elapsed > .42)
    if (!valid || !await select(selectedIndex.value + (swipe.delta < 0 ? 1 : -1))) settle()
  }
  function onWheel(event: WheelEvent) {
    if (event.ctrlKey || Math.abs(event.deltaY) < Math.abs(event.deltaX) || keys.value.length < 2) return
    const direction = event.deltaY > 0 ? 1 : -1
    const canMove = direction > 0 ? selectedIndex.value < keys.value.length - 1 : selectedIndex.value > 0
    if (performance.now() < busyUntil) { event.preventDefault(); return }
    if (!canMove) return
    event.preventDefault()
    const now = performance.now()
    if (now - lastWheel > 180 || Math.sign(wheelSum) !== Math.sign(event.deltaY)) wheelSum = 0
    wheelSum += event.deltaY * (event.deltaMode === 1 ? 16 : 1); lastWheel = now
    if (Math.abs(wheelSum) >= 30) { wheelSum = 0; void select(selectedIndex.value + direction) }
  }
  function onKeydown(event: KeyboardEvent) {
    if (event.target !== stage.value) return
    const destinations: Record<string, number> = { ArrowUp: selectedIndex.value + 1, ArrowDown: selectedIndex.value - 1, Home: 0, End: keys.value.length - 1 }
    const next = destinations[event.key]
    if (next !== undefined) { event.preventDefault(); void select(next) }
  }
  onScopeDispose(() => { for (const animation of animations) animation.cancel(); animations.clear(); cardElements.clear() })
  return { stage, isDragging, announcement, selectedIndex, depth, setCardRef, select, onPointerDown, onPointerMove, onPointerUp, onWheel, onKeydown }
}

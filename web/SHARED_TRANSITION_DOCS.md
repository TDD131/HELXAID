# Shared Element Transition System

## Design Rationale

Shared element transitions create visual continuity between UI states by keeping key elements (like the sidebar active indicator) perceptually persistent as other content changes. In a launcher with a fixed sidebar, this pattern transforms jarring content swaps into fluid, intentional navigation. The brain perceives the moving indicator as a stable anchor, reducing cognitive load and making panel switches feel like a single continuous experience rather than disconnected page loads. This is critical for a desktop launcher where users navigate frequently — smooth 200ms transitions feel responsive without causing delays, while instant swaps (without shared elements) feel abrupt and cheap.

---

## Design Tokens

```css
:root {
  --transition-ease: cubic-bezier(0.2, 0.8, 0.2, 1);
  --shared-duration: 120ms;       /* Sidebar indicator move */
  --exit-duration: 120ms;         /* Old content fade-out */
  --enter-duration: 180ms;        /* New content fade-in + translate */
  --header-crossfade: 100ms;      /* Header title crossfade */
  --translate-distance: 10px;     /* Content entrance offset */
  --stagger-item: 24ms;           /* List item stagger delay */
  --reduced-fade-duration: 60ms;  /* Reduced motion fallback */
}
```

---

## Accessibility & Testing Checklist

### Reduced Motion (`prefers-reduced-motion`)
- [ ] Enable reduced motion in OS settings
- [ ] Verify all transitions use `--reduced-fade-duration` (60ms) or instant
- [ ] Confirm no sliding/scaling animations occur
- [ ] Check that crossfades are instant

### Keyboard Navigation
- [ ] Tab through sidebar icons — focus ring is visible
- [ ] Press Enter/Space on focused icon — transition triggers
- [ ] After transition, focus remains on activated icon
- [ ] `aria-current="page"` updates correctly

### Rapid Click Handling
- [ ] Click sidebar icons rapidly in succession
- [ ] Verify no stacked/queued animations (cancelAll works)
- [ ] Final state is correct with no ghost elements
- [ ] No cloned nodes remain in DOM

### Performance (60fps Target)
- [ ] Open DevTools → Performance tab
- [ ] Record during transitions
- [ ] Verify frame times stay under 16.67ms
- [ ] Confirm only `transform` and `opacity` are animated
- [ ] Check `will-change` is applied only during active animations

### Visual Quality
- [ ] Active indicator moves smoothly between icons
- [ ] Content fades out completely before swap
- [ ] New content fades in with subtle upward translate
- [ ] Header title crossfades without layout shift
- [ ] No visible clipping, flickering, or z-index issues

### Final State Cleanup
- [ ] After transition: no inline transforms remain
- [ ] After transition: no cloned nodes in DOM
- [ ] After transition: `.shared-animating` class removed
- [ ] After transition: opacity values reset to normal

---

## Timing & Constraints Justification

The 200-250ms total perceived duration hits the sweet spot between "instant" (which lacks visual feedback) and "slow" (which users perceive as lag). Research shows 100-300ms is the ideal window for UI feedback to feel responsive. We split this into phases: 120ms for the shared element move gives the eye time to track it, while the 120ms exit + 180ms enter overlap to compress total duration. Using only `transform` and `opacity` ensures animations run on the compositor thread, avoiding main-thread layout thrashing and guaranteeing 60fps on mid-range GPUs. The 10px translate distance is subtle enough to feel natural rather than dramatic, and the stagger adds polish to lists without padding overall duration. Reduced motion users get a 60ms fade — perceptible but unobtrusive — respecting accessibility while maintaining a sense of responsiveness.

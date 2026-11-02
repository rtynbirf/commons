fix(scroll-area): make viewport keyboard-focusable

Fixes #12567

## Summary

- The scroll-area viewport renders `focus-visible` ring styles but no `tabIndex`, so in Safari/WebKit a scroll area whose content has no focusable elements cannot take keyboard focus at all. axe-core flags `scrollable-region-focusable` (WCAG 2.1.1/2.1.3, Level A). Chromium and Firefox already expose the scroller to the keyboard; WebKit does not.
- Set `tabIndex={0}` on the scrollable element in all four live registry sources: `bases/radix` (`ScrollAreaPrimitive.Viewport`), `bases/base` (`Viewport`), `bases/aria` (the scroll region is the root `overflow-auto` div; props spread through it), and the legacy `new-york-v4` source for consistency.

## Changes

- 4 files, +4 lines (`tabIndex={0}` in each). Generated artifacts under `styles/` and `public/r/` are left to the registry build.
- The component already renders `focus-visible` ring styles on the same element, so keyboard focus visibility comes for free; mouse users see no change.

## Testing

- ESLint clean on the touched files; TypeScript error list identical before/after the patch (no new errors).
- Precedent: `code-block.tsx` in the same registry already ships `tabIndex={0}` on a scrollable `<pre>`.

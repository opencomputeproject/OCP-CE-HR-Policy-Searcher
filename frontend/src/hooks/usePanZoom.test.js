import { act, renderHook } from '@testing-library/react';
import usePanZoom, { WORLD_VIEWBOX, ZOOM_BOUNDS, panBy, zoomAt } from './usePanZoom';

describe('zoomAt', () => {
  it('keeps the focal point at the same fractional position after zooming in', () => {
    const vb = WORLD_VIEWBOX;
    const fx = 300;
    const fy = 150;
    const fracXBefore = (fx - vb.x) / vb.w;
    const fracYBefore = (fy - vb.y) / vb.h;

    const next = zoomAt(vb, 2, fx, fy);

    expect((fx - next.x) / next.w).toBeCloseTo(fracXBefore, 5);
    expect((fy - next.y) / next.h).toBeCloseTo(fracYBefore, 5);
  });

  it('keeps the focal point stationary after zooming out too', () => {
    const zoomedIn = zoomAt(WORLD_VIEWBOX, 3, 600, 200);
    const fracXBefore = (600 - zoomedIn.x) / zoomedIn.w;
    const fracYBefore = (200 - zoomedIn.y) / zoomedIn.h;

    const next = zoomAt(zoomedIn, 0.5, 600, 200);

    expect((600 - next.x) / next.w).toBeCloseTo(fracXBefore, 5);
    expect((200 - next.y) / next.h).toBeCloseTo(fracYBefore, 5);
  });

  it('halves the viewBox width/height for a 2x zoom factor', () => {
    const next = zoomAt(WORLD_VIEWBOX, 2, 480, 210.75);
    expect(next.w).toBeCloseTo(480, 5);
    expect(next.h).toBeCloseTo(210.75, 5);
  });

  it('clamps zoom-in at the max-zoom bound (minW)', () => {
    const next = zoomAt(WORLD_VIEWBOX, 100, 480, 210.75, ZOOM_BOUNDS);
    expect(next.w).toBeCloseTo(ZOOM_BOUNDS.minW, 5);
  });

  it('clamps zoom-out at the full-world bound (maxW), never smaller than the world', () => {
    const zoomedIn = zoomAt(WORLD_VIEWBOX, 4, 480, 210.75);
    const next = zoomAt(zoomedIn, 0.01, 480, 210.75, ZOOM_BOUNDS);
    expect(next.w).toBeCloseTo(ZOOM_BOUNDS.maxW, 5);
    expect(next.x).toBeCloseTo(0, 5);
    expect(next.y).toBeCloseTo(0, 5);
  });

  it('keeps the aspect ratio locked to the world viewBox at any zoom', () => {
    const next = zoomAt(WORLD_VIEWBOX, 3, 100, 100);
    expect(next.h / next.w).toBeCloseTo(WORLD_VIEWBOX.h / WORLD_VIEWBOX.w, 5);
  });

  it('clamps the pan so a corner-focused zoom never crosses the world edge', () => {
    const next = zoomAt(WORLD_VIEWBOX, 4, 0, 0);
    expect(next.x).toBeGreaterThanOrEqual(0);
    expect(next.y).toBeGreaterThanOrEqual(0);
    expect(next.x + next.w).toBeLessThanOrEqual(WORLD_VIEWBOX.w + 1e-6);
    expect(next.y + next.h).toBeLessThanOrEqual(WORLD_VIEWBOX.h + 1e-6);
  });
});

describe('panBy', () => {
  it('translates the viewBox by the given world-unit delta', () => {
    const vb = { x: 100, y: 50, w: 200, h: 100 };
    const next = panBy(vb, 10, -5, ZOOM_BOUNDS);
    expect(next).toEqual({ x: 110, y: 45, w: 200, h: 100 });
  });

  it('clamps at the near (top-left) world edge', () => {
    const vb = { x: 0, y: 0, w: 200, h: 100 };
    const next = panBy(vb, -50, -50, ZOOM_BOUNDS);
    expect(next.x).toBe(0);
    expect(next.y).toBe(0);
  });

  it('clamps at the far (bottom-right) world edge', () => {
    const vb = { x: 700, y: 300, w: 200, h: 100 };
    const next = panBy(vb, 500, 500, ZOOM_BOUNDS);
    expect(next.x).toBe(ZOOM_BOUNDS.w - 200);
    expect(next.y).toBe(ZOOM_BOUNDS.h - 100);
  });
});

describe('WORLD_VIEWBOX', () => {
  it('matches the verified atlas viewBox (0 0 960 421.5)', () => {
    expect(WORLD_VIEWBOX).toEqual({ x: 0, y: 0, w: 960, h: 421.5 });
  });
});

describe('usePanZoom (hook integration)', () => {
  // Reduced-motion forces animateTo() to apply the target viewBox
  // synchronously instead of stepping through requestAnimationFrame, so
  // these assertions don't need to pump animation frames.
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    window.matchMedia = jest.fn((query) => ({
      matches: true,
      media: query,
      addListener: () => {},
      removeListener: () => {},
    }));
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('starts at the full world view with zoom-out/reset disabled', () => {
    const ref = { current: null };
    const { result } = renderHook(() => usePanZoom(ref));

    expect(result.current.viewBox).toEqual(WORLD_VIEWBOX);
    expect(result.current.canZoomOut).toBe(false);
    expect(result.current.canZoomIn).toBe(true);
  });

  it('zoomIn narrows the viewBox and enables zoom-out/reset', () => {
    const ref = { current: null };
    const { result } = renderHook(() => usePanZoom(ref));

    act(() => result.current.zoomIn());

    expect(result.current.viewBox.w).toBeLessThan(WORLD_VIEWBOX.w);
    expect(result.current.canZoomOut).toBe(true);
  });

  it('reset restores the initial full-world viewBox after zooming', () => {
    const ref = { current: null };
    const { result } = renderHook(() => usePanZoom(ref));

    act(() => result.current.zoomIn());
    act(() => result.current.zoomIn());
    expect(result.current.viewBox).not.toEqual(WORLD_VIEWBOX);

    act(() => result.current.reset());

    expect(result.current.viewBox).toEqual(WORLD_VIEWBOX);
    expect(result.current.canZoomOut).toBe(false);
  });

  it('repeated zoomIn clamps at max zoom and disables further zoom-in', () => {
    const ref = { current: null };
    const { result } = renderHook(() => usePanZoom(ref));

    act(() => {
      for (let i = 0; i < 20; i += 1) result.current.zoomIn();
    });

    expect(result.current.viewBox.w).toBeCloseTo(ZOOM_BOUNDS.minW, 5);
    expect(result.current.canZoomIn).toBe(false);
  });

  describe('zoomToward', () => {
    it('narrows the viewBox by the given factor, centered on the given world point', () => {
      const ref = { current: null };
      const { result } = renderHook(() => usePanZoom(ref));

      act(() => result.current.zoomToward(205.8, 84, 2));

      expect(result.current.viewBox.w).toBeCloseTo(WORLD_VIEWBOX.w / 2, 5);
      expect(result.current.canZoomOut).toBe(true);
      // The focal point stays at the same fractional position it started at.
      const { viewBox } = result.current;
      expect((205.8 - viewBox.x) / viewBox.w).toBeCloseTo((205.8 - WORLD_VIEWBOX.x) / WORLD_VIEWBOX.w, 5);
    });

    it('is independent of the current viewBox center, unlike zoomIn', () => {
      const ref = { current: null };
      const { result } = renderHook(() => usePanZoom(ref));

      act(() => result.current.zoomToward(50, 50, 3));

      const { viewBox } = result.current;
      // Zooming toward a point in the far corner should pull the viewBox
      // origin toward that corner, not stay anchored on the world center.
      expect(viewBox.x).toBeLessThan(WORLD_VIEWBOX.w / 2 - viewBox.w / 2);
    });
  });
});

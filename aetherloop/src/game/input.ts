export type Action = 'jump' | 'dash' | 'echo' | 'pulse' | 'dissolve' | 'pause';

const KEYMAP: Record<string, Action> = {
  Space: 'jump', ShiftLeft: 'dash', ShiftRight: 'dash', KeyE: 'echo',
  KeyF: 'pulse', KeyQ: 'dissolve', KeyP: 'pause', Escape: 'pause',
};

export class Input {
  enabled = false;
  locked = false;
  sensitivity = 1;
  stick = { x: 0, y: 0 };
  onUnlock?: () => void;
  private down = new Set<string>();
  private queued = new Set<Action>();
  private lookX = 0;
  private lookY = 0;
  private dragging = false;
  private cleanup: (() => void)[] = [];

  constructor(private canvas: HTMLCanvasElement) {
    const on = <K extends keyof WindowEventMap>(t: K, f: (e: WindowEventMap[K]) => void, target: Window | Document | HTMLElement = window) => {
      target.addEventListener(t, f as EventListener);
      this.cleanup.push(() => target.removeEventListener(t, f as EventListener));
    };
    on('keydown', (e) => {
      if (!this.enabled) return;
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault();
      if (!e.repeat && KEYMAP[e.code]) this.queued.add(KEYMAP[e.code]);
      this.down.add(e.code);
    });
    on('keyup', (e) => this.down.delete(e.code));
    on('blur', () => { this.down.clear(); this.dragging = false; });
    on('mousedown', (e) => {
      if (!this.enabled || e.target !== this.canvas) return;
      if (this.locked) {
        if (e.button === 0) this.queued.add('pulse');
        return;
      }
      this.dragging = true;
      try {
        const r = this.canvas.requestPointerLock() as unknown as Promise<void> | undefined;
        if (r && typeof r.catch === 'function') r.catch(() => {});
      } catch { /* pointer lock unavailable — drag-to-look still works */ }
    });
    on('mouseup', () => { this.dragging = false; });
    on('mousemove', (e) => {
      if (!this.enabled) return;
      if (this.locked || this.dragging) {
        this.lookX += e.movementX;
        this.lookY += e.movementY;
      }
    });
    const plc = () => {
      const was = this.locked;
      this.locked = document.pointerLockElement === this.canvas;
      if (was && !this.locked) this.onUnlock?.();
    };
    document.addEventListener('pointerlockchange', plc);
    this.cleanup.push(() => document.removeEventListener('pointerlockchange', plc));
  }

  trigger(a: Action) { if (this.enabled) this.queued.add(a); }
  addLook(dx: number, dy: number) { this.lookX += dx; this.lookY += dy; }
  consume(a: Action) { const had = this.queued.has(a); this.queued.delete(a); return had; }
  clearQueue() { this.queued.clear(); }

  takeLook() {
    const r = { x: this.lookX * this.sensitivity, y: this.lookY * this.sensitivity };
    this.lookX = 0; this.lookY = 0;
    return r;
  }

  axis() {
    const d = (c: string) => (this.down.has(c) ? 1 : 0);
    let x = d('KeyD') + d('ArrowRight') - d('KeyA') - d('ArrowLeft') + this.stick.x;
    let y = d('KeyW') + d('ArrowUp') - d('KeyS') - d('ArrowDown') + this.stick.y;
    const len = Math.hypot(x, y);
    if (len > 1) { x /= len; y /= len; }
    return { x, y };
  }

  exitLock() { if (document.pointerLockElement) document.exitPointerLock(); }

  dispose() { this.cleanup.forEach((f) => f()); this.exitLock(); }
}

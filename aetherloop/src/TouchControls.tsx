import { useRef, useState } from 'react';
import type { Input, Action } from './game/input';

export default function TouchControls({ input, onPause }: { input: Input; onPause: () => void }) {
  const stickId = useRef<number | null>(null);
  const lookId = useRef<number | null>(null);
  const origin = useRef({ x: 0, y: 0 });
  const last = useRef({ x: 0, y: 0 });
  const [knob, setKnob] = useState<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const onStart = (e: React.TouchEvent) => {
    for (const t of Array.from(e.changedTouches)) {
      if (t.clientX < window.innerWidth * 0.45 && stickId.current === null) {
        stickId.current = t.identifier; origin.current = { x: t.clientX, y: t.clientY };
        setKnob({ x: 0, y: 0, ox: t.clientX, oy: t.clientY });
      } else if (lookId.current === null) {
        lookId.current = t.identifier; last.current = { x: t.clientX, y: t.clientY };
      }
    }
  };
  const onMove = (e: React.TouchEvent) => {
    for (const t of Array.from(e.changedTouches)) {
      if (t.identifier === stickId.current) {
        let dx = t.clientX - origin.current.x, dy = t.clientY - origin.current.y;
        const len = Math.hypot(dx, dy), max = 55;
        if (len > max) { dx = (dx / len) * max; dy = (dy / len) * max; }
        input.stick.x = dx / max; input.stick.y = -dy / max;
        setKnob((k) => (k ? { ...k, x: dx, y: dy } : k));
      } else if (t.identifier === lookId.current) {
        input.addLook((t.clientX - last.current.x) * 2.2, (t.clientY - last.current.y) * 2.2);
        last.current = { x: t.clientX, y: t.clientY };
      }
    }
  };
  const onEnd = (e: React.TouchEvent) => {
    for (const t of Array.from(e.changedTouches)) {
      if (t.identifier === stickId.current) { stickId.current = null; input.stick.x = 0; input.stick.y = 0; setKnob(null); }
      if (t.identifier === lookId.current) lookId.current = null;
    }
  };
  const btn = (a: Action, label: string, cls = '') => (
    <button className={`tbtn ${cls}`} onTouchStart={(e) => { e.stopPropagation(); input.trigger(a); }}>{label}</button>
  );
  return (
    <div className="touch" onTouchStart={onStart} onTouchMove={onMove} onTouchEnd={onEnd} onTouchCancel={onEnd}>
      {knob && (
        <div className="stick" style={{ left: knob.ox - 60, top: knob.oy - 60 }}>
          <div className="knob" style={{ transform: `translate(${knob.x}px, ${knob.y}px)` }} />
        </div>
      )}
      <div className="tbtns">
        {btn('echo', 'ECHO', 'echo')}
        {btn('pulse', 'PULSE')}
        {btn('dash', 'DASH')}
        {btn('jump', 'JUMP', 'big')}
      </div>
      <button className="tpause" onTouchStart={(e) => { e.stopPropagation(); onPause(); }}>❚❚</button>
      <button className="tdissolve" onTouchStart={(e) => { e.stopPropagation(); input.trigger('dissolve'); }}>Q</button>
    </div>
  );
}

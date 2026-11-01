import { useCallback, useEffect, useRef, useState } from 'react';
import { Game, type HudState, type RunStats } from './game/engine';
import { safeGet, safeSet } from './game/util';
import TouchControls from './TouchControls';

type Screen = 'menu' | 'how' | 'settings' | 'playing' | 'paused' | 'complete' | 'over';
interface Toast { id: number; msg: string; tone: 'info' | 'good' | 'bad' }

const isTouch = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches;
const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export default function App() {
  const mount = useRef<HTMLDivElement>(null);
  const game = useRef<Game | null>(null);
  const [screen, setScreen] = useState<Screen>('menu');
  const [prevScreen, setPrevScreen] = useState<Screen>('menu');
  const [hud, setHud] = useState<HudState | null>(null);
  const [stats, setStats] = useState<RunStats | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [muted, setMuted] = useState(safeGet('aetherloop.muted') === '1');
  const [quality, setQuality] = useState<'high' | 'low'>((safeGet('aetherloop.quality') as 'high' | 'low') || (isTouch ? 'low' : 'high'));
  const [sens, setSens] = useState(Number(safeGet('aetherloop.sens') ?? 1) || 1);
  const [webglError, setWebglError] = useState(false);

  const toast = useCallback((msg: string, tone: Toast['tone'] = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, msg, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3600);
  }, []);

  useEffect(() => {
    let g: Game;
    try {
      g = new Game(mount.current!, {
        onHud: setHud,
        onLevelComplete: (s) => { setStats(s); setScreen('complete'); },
        onGameOver: (s) => { setStats(s); setScreen('over'); },
        onToast: toast,
        onPauseRequest: () => { game.current?.pause(); setScreen((s) => (s === 'playing' ? 'paused' : s)); },
      });
    } catch (e) {
      console.error(e); setWebglError(true); return;
    }
    game.current = g;
    if (import.meta.env.DEV) (window as unknown as { __game: Game }).__game = g;
    return () => { g.dispose(); game.current = null; };
  }, [toast]);

  useEffect(() => { game.current?.setMuted(muted); safeSet('aetherloop.muted', muted ? '1' : '0'); }, [muted]);
  useEffect(() => { game.current?.setQuality(quality); safeSet('aetherloop.quality', quality); }, [quality]);
  useEffect(() => { game.current?.setSensitivity(sens); safeSet('aetherloop.sens', String(sens)); }, [sens]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (screen === 'paused' && (e.code === 'Escape' || e.code === 'KeyP')) { game.current?.resume(); setScreen('playing'); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [screen]);

  const g = () => game.current!;
  const play = () => { g().newRun(); setScreen('playing'); };
  const resume = () => { g().resume(); setScreen('playing'); };
  const next = () => { g().nextLevel(); setScreen('playing'); };
  const retry = () => { g().retryLevel(); setScreen('playing'); };
  const menu = () => { g().toMenu(); setScreen('menu'); };
  const openSettings = () => { setPrevScreen(screen); setScreen('settings'); };

  if (webglError) {
    return <div className="overlay"><div className="panel"><h2>WebGL unavailable</h2><p>Aetherloop needs a browser with WebGL enabled.</p></div></div>;
  }

  return (
    <div className="app">
      <div ref={mount} className="viewport" />

      {screen === 'playing' && hud && <Hud hud={hud} />}
      {screen === 'playing' && isTouch && game.current && <TouchControls input={game.current.input} onPause={() => { g().pause(); setScreen('paused'); }} />}
      {screen === 'playing' && !isTouch && <div className="hint">Click to aim · WASD move · Space jump ×2 · Shift dash · E echo · F/click pulse · Q dissolve · Esc pause</div>}

      <div className="toasts">{toasts.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.msg}</div>)}</div>

      {screen === 'menu' && (
        <div className="overlay menu">
          <div className="title-wrap">
            <div className="kicker">A sky-island odyssey</div>
            <h1 className="title">AETHER<span>LOOP</span></h1>
            <p className="tagline">Record echoes of yourself. Solve the sky together — with you.</p>
          </div>
          <div className="menu-buttons">
            <button className="btn primary" onClick={play}>Begin the Ascent</button>
            <button className="btn" onClick={() => setScreen('how')}>How to Play</button>
            <button className="btn" onClick={openSettings}>Settings</button>
          </div>
          <div className="best">Best score · {g()?.getBest?.() ?? 0}</div>
          <div className="foot">Original game · procedurally generated worlds · synthesized soundtrack</div>
        </div>
      )}

      {screen === 'how' && (
        <div className="overlay">
          <div className="panel wide">
            <h2>How to Play</h2>
            <div className="how-grid">
              <section><h3>The Goal</h3><p>Each sky archipelago is sealed by a <b>Skygate</b>. Gather enough <b>Aether Shards</b>, then power <b>every Resonance Pad</b> around the gate <i>at the same time</i> to break the Seal and enter the portal.</p></section>
              <section><h3>Echoes ✦</h3><p>The pads are too far apart for one Wayfarer. Press <kbd>E</kbd> to start recording, move to a pad, press <kbd>E</kbd> again. Your <b>Echo</b> replays your exact path from where you started and then <b>stays</b> where you ended. Stack echoes to hold multiple pads.</p></section>
              <section><h3>The Hollows</h3><p>Dark shapes pour from rifts. They hunt you <i>and your Echoes</i> — three hits shatter an Echo. <kbd>F</kbd>/click releases a <b>Pulse</b>; a <b>dash</b> through a Hollow destroys it.</p></section>
              <section><h3>Controls</h3><p><kbd>WASD</kbd> move · <kbd>Mouse</kbd> camera · <kbd>Space</kbd> jump (double jump in the air) · <kbd>Shift</kbd> dash · <kbd>E</kbd> record/release Echo · <kbd>Q</kbd> dissolve Echoes · <kbd>F</kbd> pulse · <kbd>Esc</kbd> pause. On touch: left stick, drag right side to look, buttons for actions.</p></section>
            </div>
            <button className="btn primary" onClick={() => setScreen('menu')}>Got it</button>
          </div>
        </div>
      )}

      {screen === 'settings' && (
        <div className="overlay">
          <div className="panel">
            <h2>Settings</h2>
            <label className="row"><span>Sound</span><button className="btn small" onClick={() => setMuted((m) => !m)}>{muted ? 'Off' : 'On'}</button></label>
            <label className="row"><span>Graphics</span><button className="btn small" onClick={() => setQuality((q) => (q === 'high' ? 'low' : 'high'))}>{quality === 'high' ? 'High (bloom + shadows)' : 'Performance'}</button></label>
            <label className="row"><span>Look sensitivity · {sens.toFixed(1)}</span><input type="range" min={0.3} max={2.5} step={0.1} value={sens} onChange={(e) => setSens(Number(e.target.value))} /></label>
            <button className="btn primary" onClick={() => setScreen(prevScreen)}>Back</button>
          </div>
        </div>
      )}

      {screen === 'paused' && (
        <div className="overlay">
          <div className="panel">
            <h2>Paused</h2>
            <button className="btn primary" onClick={resume}>Resume</button>
            <button className="btn" onClick={openSettings}>Settings</button>
            <button className="btn" onClick={retry}>Restart Level</button>
            <button className="btn" onClick={menu}>Main Menu</button>
          </div>
        </div>
      )}

      {screen === 'complete' && stats && (
        <div className="overlay">
          <div className="panel">
            <div className="kicker">Skygate crossed</div>
            <h2>Level {stats.level} complete</h2>
            <Stats s={stats} />
            <button className="btn primary" onClick={next}>Ascend to Level {stats.level + 1}</button>
            <button className="btn" onClick={menu}>Main Menu</button>
          </div>
        </div>
      )}

      {screen === 'over' && stats && (
        <div className="overlay">
          <div className="panel">
            <div className="kicker bad">Your light has faded</div>
            <h2>Game Over</h2>
            <Stats s={stats} />
            <button className="btn primary" onClick={retry}>Retry Level {stats.level}</button>
            <button className="btn" onClick={play}>New Run</button>
            <button className="btn" onClick={menu}>Main Menu</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Stats({ s }: { s: RunStats }) {
  return (
    <div className="stats">
      <div><span>Time</span><b>{fmtTime(s.time)}</b></div>
      <div><span>Shards (run)</span><b>{s.shards}</b></div>
      <div><span>Hollows banished</span><b>{s.kills}</b></div>
      {s.bonus > 0 && <div><span>Level bonus</span><b>+{s.bonus}</b></div>}
      <div className="total"><span>Score</span><b>{s.score}</b></div>
      <div><span>{s.newBest ? '★ New best!' : 'Best'}</span><b>{s.best}</b></div>
    </div>
  );
}

function Hud({ hud }: { hud: HudState }) {
  return (
    <div className="hud">
      <div className="hud-tl">
        <div className="lvl">Level {hud.level} · <span>{hud.biome}</span></div>
        <div className="hearts">
          {Array.from({ length: hud.maxHealth }, (_, i) => <i key={i} className={i < hud.health ? 'on' : ''} />)}
        </div>
        <div className="shards">◆ {hud.shards}<small>/{hud.shardsNeeded} needed · {hud.shardsTotal} total</small></div>
      </div>
      <div className="hud-tr">
        <div className="score">{hud.score.toLocaleString()}</div>
        <div className="time">{fmtTime(hud.time)}</div>
      </div>
      <div className="objective">
        <div className="compass" style={{ transform: `rotate(${hud.objAngle}rad)` }}>▲</div>
        <div><div className="obj-text">{hud.objective}</div><div className="obj-dist">{Math.round(hud.objDist)} m</div></div>
      </div>
      <div className="abilities">
        <Ability label="Echo" keyName="E" value={hud.recording ? hud.recordFrac : 0} active={hud.recording}
          sub={hud.recording ? 'REC' : `${hud.echoes}/${hud.maxEchoes}`} />
        <Ability label="Pulse" keyName="F" value={hud.pulseCd} cooldown />
        <Ability label="Dash" keyName="⇧" value={hud.dashCd} cooldown />
        <div className="pads">
          {Array.from({ length: hud.padsNeeded }, (_, i) => <i key={i} className={i < hud.padsActive ? 'on' : ''} />)}
          <span>{hud.gateOpen ? 'Gate open' : 'Pads'}</span>
        </div>
      </div>
    </div>
  );
}

function Ability({ label, keyName, value, cooldown, active, sub }: { label: string; keyName: string; value: number; cooldown?: boolean; active?: boolean; sub?: string }) {
  const deg = Math.round((cooldown ? 1 - value : value) * 360);
  const ready = cooldown ? value <= 0 : true;
  return (
    <div className={`ability ${ready ? 'ready' : ''} ${active ? 'rec' : ''} ${cooldown ? 'cd' : ''}`}>
      <div className="dial" style={{ background: `conic-gradient(var(--fill) ${deg}deg, rgba(255,255,255,0.08) ${deg}deg)` }}>
        <div className="dial-in"><b>{keyName}</b>{sub && <small>{sub}</small>}</div>
      </div>
      <span>{label}</span>
    </div>
  );
}

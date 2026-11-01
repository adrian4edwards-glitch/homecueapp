// Fully procedural audio: every sound and the ambient score is synthesized live (no licensed assets).
const PENTA = [0, 3, 5, 7, 10, 12, 15, 17];

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private master!: GainNode;
  private sfxBus!: GainNode;
  private musicBus!: GainNode;
  private reverb!: ConvolverNode;
  private drone: { stop: () => void } | null = null;
  private arpTimer: number | null = null;
  muted = false;

  init() {
    if (this.ctx) { void this.ctx.resume(); return; }
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.gain.value = this.muted ? 0 : 0.7;
    this.master.connect(ctx.destination);
    this.reverb = ctx.createConvolver();
    this.reverb.buffer = this.impulse(3.2);
    const wet = ctx.createGain(); wet.gain.value = 0.45;
    this.reverb.connect(wet).connect(this.master);
    this.sfxBus = ctx.createGain(); this.sfxBus.gain.value = 0.8;
    this.sfxBus.connect(this.master); this.sfxBus.connect(this.reverb);
    this.musicBus = ctx.createGain(); this.musicBus.gain.value = 0.32;
    this.musicBus.connect(this.master); this.musicBus.connect(this.reverb);
  }

  setMuted(m: boolean) {
    this.muted = m;
    if (this.ctx) this.master.gain.setTargetAtTime(m ? 0 : 0.7, this.ctx.currentTime, 0.05);
  }

  private impulse(seconds: number) {
    const ctx = this.ctx!;
    const len = Math.floor(ctx.sampleRate * seconds);
    const buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = buf.getChannelData(c);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6);
    }
    return buf;
  }

  private tone(freq: number, dur: number, type: OscillatorType = 'sine', vol = 0.25, slideTo?: number, delay = 0, bus?: GainNode) {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime + delay;
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(bus ?? this.sfxBus);
    o.start(t); o.stop(t + dur + 0.05);
  }

  private noise(dur: number, vol: number, f0: number, f1: number, q = 1) {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const src = ctx.createBufferSource(); src.buffer = buf;
    const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.Q.value = q;
    f.frequency.setValueAtTime(f0, t); f.frequency.exponentialRampToValueAtTime(f1, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f).connect(g).connect(this.sfxBus);
    src.start(t);
  }

  jump() { this.tone(380, 0.16, 'triangle', 0.18, 720); }
  doubleJump() { this.tone(520, 0.2, 'triangle', 0.18, 1100); this.noise(0.25, 0.12, 2000, 6000, 2); }
  land() { this.noise(0.08, 0.1, 400, 120, 1); }
  dash() { this.noise(0.3, 0.25, 600, 4000, 1.5); this.tone(200, 0.2, 'sawtooth', 0.06, 90); }
  shard(i = 0) {
    const base = 660 * Math.pow(2, (i % 5) / 12);
    [0, 4, 7, 12].forEach((s, k) => this.tone(base * Math.pow(2, s / 12), 0.35, 'sine', 0.16, undefined, k * 0.055));
  }
  pulse() { this.noise(0.6, 0.35, 200, 3000, 0.8); this.tone(120, 0.5, 'sine', 0.35, 40); }
  hit() { this.tone(160, 0.3, 'square', 0.12, 60); this.noise(0.25, 0.25, 900, 200, 1); }
  kill() { this.tone(900, 0.18, 'sine', 0.12, 1800); this.noise(0.2, 0.15, 3000, 8000, 3); }
  recStart() { this.tone(440, 0.25, 'sine', 0.2, 880); this.tone(660, 0.25, 'sine', 0.12, 1320, 0.08); }
  recRelease() { [880, 660, 440, 330].forEach((f, i) => this.tone(f, 0.3, 'triangle', 0.14, undefined, i * 0.05)); }
  echoBreak() { this.noise(0.5, 0.25, 4000, 300, 2); this.tone(300, 0.4, 'sawtooth', 0.08, 80); }
  pad(on: boolean) { this.tone(on ? 523 : 392, 0.25, 'sine', 0.15, on ? 784 : 262); }
  gate() {
    [0, 7, 12, 16, 19, 24].forEach((s, i) => this.tone(220 * Math.pow(2, s / 12), 1.4, 'sine', 0.13, undefined, i * 0.09));
    this.noise(1.6, 0.2, 300, 6000, 0.7);
  }
  portal() { this.tone(200, 1.2, 'sine', 0.25, 1600); this.noise(1.2, 0.2, 400, 9000, 1); }
  fall() { this.tone(600, 0.7, 'sine', 0.18, 80); }
  denied() { this.tone(180, 0.18, 'square', 0.08); this.tone(150, 0.2, 'square', 0.08, undefined, 0.12); }

  startMusic(rootHz: number) {
    const ctx = this.ctx; if (!ctx) return;
    this.stopMusic();
    const t = ctx.currentTime;
    const filter = ctx.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = 700; filter.Q.value = 3;
    const lfo = ctx.createOscillator(); lfo.frequency.value = 0.07;
    const lfoGain = ctx.createGain(); lfoGain.gain.value = 420;
    lfo.connect(lfoGain).connect(filter.frequency); lfo.start();
    const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.5, t + 4);
    filter.connect(g).connect(this.musicBus);
    const oscs: OscillatorNode[] = [];
    [0, 7, 12, 15, 19].forEach((s, i) => {
      for (const det of [-7, 7]) {
        const o = ctx.createOscillator();
        o.type = i < 2 ? 'sawtooth' : 'triangle';
        o.frequency.value = rootHz * Math.pow(2, s / 12);
        o.detune.value = det;
        const og = ctx.createGain(); og.gain.value = 0.06;
        o.connect(og).connect(filter); o.start(); oscs.push(o);
      }
    });
    this.drone = {
      stop: () => {
        const now = ctx.currentTime;
        g.gain.cancelScheduledValues(now);
        g.gain.setTargetAtTime(0.0001, now, 0.6);
        oscs.forEach((o) => o.stop(now + 3)); lfo.stop(now + 3);
      },
    };
    let step = 0;
    this.arpTimer = window.setInterval(() => {
      if (Math.random() < 0.35) { step++; return; }
      const s = PENTA[(step * 3 + Math.floor(Math.random() * 3)) % PENTA.length];
      this.tone(rootHz * 4 * Math.pow(2, s / 12), 1.6, 'sine', 0.05, undefined, 0, this.musicBus);
      step++;
    }, 420);
  }

  stopMusic() {
    this.drone?.stop(); this.drone = null;
    if (this.arpTimer !== null) { clearInterval(this.arpTimer); this.arpTimer = null; }
  }
}

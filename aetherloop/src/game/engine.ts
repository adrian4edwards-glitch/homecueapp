import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { AudioEngine } from './audio';
import { biomeFor, type Biome } from './biomes';
import { animateAvatar, buildAvatar, buildHollow, cloudTexture, makeSky, Particles, softTexture, type Avatar } from './fx';
import { Input } from './input';
import { clamp, damp, safeGet, safeSet } from './util';
import { Level, type Platform } from './world';

export interface HudState {
  level: number; biome: string; health: number; maxHealth: number;
  shards: number; shardsNeeded: number; shardsTotal: number;
  echoes: number; maxEchoes: number; recording: boolean; recordFrac: number;
  padsActive: number; padsNeeded: number; gateOpen: boolean;
  score: number; time: number; pulseCd: number; dashCd: number;
  objective: string; objAngle: number; objDist: number; best: number;
}
export interface RunStats { level: number; time: number; shards: number; kills: number; score: number; bonus: number; best: number; newBest: boolean }
export interface GameEvents {
  onHud: (h: HudState) => void;
  onLevelComplete: (s: RunStats) => void;
  onGameOver: (s: RunStats) => void;
  onToast: (msg: string, tone?: 'info' | 'good' | 'bad') => void;
  onPauseRequest: () => void;
}

type Mode = 'menu' | 'playing' | 'paused' | 'transition' | 'over';
interface Sample { t: number; x: number; y: number; z: number; ry: number; sp: number }
interface Echo { avatar: Avatar; samples: Sample[]; playT: number; pos: THREE.Vector3; hp: number; done: boolean; flash: number }
interface Hollow { group: THREE.Group; shell: THREE.Object3D; pos: THREE.Vector3; vel: THREE.Vector3; home: THREE.Vector3; seed: number; spawnT: number }

const GRAVITY = 30, MOVE_SPEED = 8.5, JUMP_V = 11.5, DJUMP_V = 10.5, DASH_V = 23, DASH_T = 0.17;
const MAX_HEALTH = 6, REC_MAX = 12, PULSE_CD = 2.2, DASH_CD = 0.85, PULSE_R = 6.5;

export class Game {
  readonly input: Input;
  readonly audio = new AudioEngine();
  private renderer: THREE.WebGLRenderer;
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(62, 1, 0.1, 2000);
  private hemi = new THREE.HemisphereLight('#ffffff', '#333333', 1);
  private sun = new THREE.DirectionalLight('#ffffff', 2);
  private sky!: THREE.Mesh;
  private particles = new Particles();
  private clouds: THREE.Sprite[] = [];
  private motes!: THREE.Points;
  private level!: Level;
  private biome!: Biome;
  private player: Avatar;
  private mode: Mode = 'menu';
  private raf = 0;
  private clock = new THREE.Clock();
  private t = 0;
  private quality: 'high' | 'low' = 'high';

  // player state
  private pos = new THREE.Vector3();
  private vel = new THREE.Vector3();
  private facing = 0;
  private grounded = false;
  private ground: Platform | null = null;
  private lastGroundT = 0;
  private jumps = 0;
  private dashT = 0; private dashCd = 0; private pulseCd = 0; private invuln = 0;
  private checkpoint = new THREE.Vector3();
  private health = MAX_HEALTH;
  private yaw = 0.6; private pitch = 0.35; private camDist = 9;
  private camPos = new THREE.Vector3();

  // run state
  private levelNum = 1; private score = 0; private levelStartScore = 0;
  private levelTime = 0; private kills = 0; private shardsGot = 0;
  private best = Number(safeGet('aetherloop.best') ?? 0) || 0;

  // echo state
  private recording = false; private rec: Sample[] = []; private recT = 0;
  private echoes: Echo[] = [];
  private hollows: Hollow[] = [];
  private gateOpen = false; private warnedShards = false; private padsActiveCount = 0;
  private hudTimer = 0;
  private tmp = new THREE.Vector3();
  private tmp2 = new THREE.Vector3();
  private col = { accent: new THREE.Color(), accent2: new THREE.Color(), hollow: new THREE.Color(), white: new THREE.Color('#ffffff') };

  constructor(private container: HTMLElement, private ev: GameEvents) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.style.display = 'block';
    this.input = new Input(this.renderer.domElement);
    this.input.onUnlock = () => { if (this.mode === 'playing') this.ev.onPauseRequest(); };

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.85, 0.55, 0.8);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.scene.add(this.hemi, this.sun, this.sun.target, this.particles.points);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    const sc = this.sun.shadow.camera; sc.left = -32; sc.right = 32; sc.top = 32; sc.bottom = -32; sc.near = 1; sc.far = 140;
    this.sun.shadow.bias = -0.0005; this.sun.shadow.normalBias = 0.03;

    this.buildAtmosphere();
    this.player = buildAvatar('#59f3ff');
    this.player.root.traverse((o) => { o.castShadow = true; });
    this.scene.add(this.player.root);

    this.loadLevel(1);
    window.addEventListener('resize', this.resize);
    this.resize();
    this.clock.start();
    this.loop();
  }

  // ---------- public API used by the React shell ----------
  newRun() {
    this.audio.init();
    this.score = 0; this.health = MAX_HEALTH; this.kills = 0; this.shardsGot = 0;
    this.loadLevel(1); this.beginPlay();
  }
  nextLevel() {
    this.health = Math.min(MAX_HEALTH, this.health + 2);
    this.loadLevel(this.levelNum + 1); this.beginPlay();
  }
  retryLevel() {
    this.audio.init();
    this.score = this.levelStartScore; this.health = MAX_HEALTH;
    this.loadLevel(this.levelNum); this.beginPlay();
  }
  pause() { if (this.mode === 'playing') { this.mode = 'paused'; this.input.enabled = false; this.input.exitLock(); } }
  resume() { if (this.mode === 'paused') { this.mode = 'playing'; this.input.enabled = true; this.input.clearQueue(); this.clock.getDelta(); } }
  toMenu() { this.mode = 'menu'; this.input.enabled = false; this.input.exitLock(); this.audio.stopMusic(); }
  setMuted(m: boolean) { this.audio.setMuted(m); }
  setSensitivity(s: number) { this.input.sensitivity = s; }
  setQuality(q: 'high' | 'low') {
    this.quality = q;
    this.renderer.setPixelRatio(q === 'high' ? Math.min(window.devicePixelRatio, 1.5) : 1);
    this.renderer.shadowMap.enabled = q === 'high';
    this.sun.castShadow = q === 'high';
    this.bloom.enabled = q === 'high';
    this.scene.traverse((o) => { const m = (o as THREE.Mesh).material as THREE.Material | undefined; if (m && 'needsUpdate' in m) m.needsUpdate = true; });
    this.resize();
  }
  getBest() { return this.best; }

  dispose() {
    cancelAnimationFrame(this.raf);
    window.removeEventListener('resize', this.resize);
    this.input.dispose(); this.audio.stopMusic();
    this.level?.dispose();
    this.renderer.dispose(); this.composer.dispose();
    this.renderer.domElement.remove();
  }

  // ---------- setup ----------
  private buildAtmosphere() {
    const cloudTex = cloudTexture();
    for (let i = 0; i < 70; i++) {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: cloudTex, transparent: true, depthWrite: false, opacity: 0.55 }));
      const a = Math.random() * Math.PI * 2, d = 20 + Math.random() * 260, size = 40 + Math.random() * 70;
      s.position.set(Math.cos(a) * d, -28 - Math.random() * 45, Math.sin(a) * d);
      s.scale.set(size, size * 0.5, 1);
      this.clouds.push(s); this.scene.add(s);
    }
    const n = 700; const p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { p[i * 3] = (Math.random() - 0.5) * 220; p[i * 3 + 1] = Math.random() * 60 - 20; p[i * 3 + 2] = (Math.random() - 0.5) * 220; }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3));
    this.motes = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.35, map: softTexture(64), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, color: '#ffffff', opacity: 0.8 }));
    this.scene.add(this.motes);
  }

  private applyBiome(b: Biome) {
    this.biome = b;
    if (this.sky) { this.scene.remove(this.sky); this.sky.geometry.dispose(); (this.sky.material as THREE.Material).dispose(); }
    this.sky = makeSky(b); this.scene.add(this.sky);
    this.scene.fog = new THREE.FogExp2(b.fog, b.fogDensity);
    this.hemi.color.set(b.skyHorizon); this.hemi.groundColor.set(b.rock); this.hemi.intensity = b.hemi;
    this.sun.color.set(b.sun); this.sun.intensity = b.sunIntensity;
    this.clouds.forEach((c) => c.material.color.set(b.cloud));
    (this.motes.material as THREE.PointsMaterial).color.set(b.accent);
    this.col.accent.set(b.accent); this.col.accent2.set(b.accent2); this.col.hollow.set(b.hollow);
  }

  private loadLevel(n: number) {
    this.levelNum = n;
    this.level?.dispose();
    this.clearEntities();
    const b = biomeFor(n);
    this.applyBiome(b);
    this.level = new Level(n, b, 1337 + n * 7919);
    this.scene.add(this.level.group);
    this.pos.copy(this.level.start); this.vel.set(0, 0, 0);
    this.checkpoint.copy(this.level.start);
    this.facing = Math.atan2(this.level.goal.x - this.pos.x, this.level.goal.z - this.pos.z);
    this.yaw = this.facing + Math.PI; this.pitch = 0.32;
    this.camPos.set(this.pos.x + Math.sin(this.yaw) * 10, this.pos.y + 5, this.pos.z + Math.cos(this.yaw) * 10);
    this.gateOpen = false; this.warnedShards = false; this.levelTime = 0;
    this.recording = false; this.rec = [];
    this.dashCd = 0; this.pulseCd = 0; this.invuln = 0;
    this.levelStartScore = this.score;
    this.particles.clear();
    this.emitHud(true);
  }

  private clearEntities() {
    this.echoes.forEach((e) => this.scene.remove(e.avatar.root)); this.echoes = [];
    this.hollows.forEach((h) => this.scene.remove(h.group)); this.hollows = [];
  }

  private beginPlay() {
    this.mode = 'playing'; this.input.enabled = true; this.input.clearQueue();
    this.audio.startMusic(this.biome.rootHz);
    this.ev.onToast(`Level ${this.levelNum} · ${this.biome.name}`, 'info');
    if (this.levelNum === 1) setTimeout(() => this.ev.onToast('Follow the beam of light. Collect Aether Shards.', 'info'), 2200);
  }

  private resize = () => {
    const w = this.container.clientWidth || window.innerWidth, h = this.container.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h); this.composer.setSize(w, h);
    this.bloom.resolution.set(w / 2, h / 2);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  };

  // ---------- main loop ----------
  private loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    const dt = Math.min(this.clock.getDelta(), 0.05);
    this.t += dt;
    this.level.update(this.t, dt);
    if (this.mode === 'playing') this.updatePlay(dt);
    else if (this.mode === 'menu') this.updateAttract(dt);
    if (this.mode !== 'paused') this.particles.update(dt);
    this.updateAmbient(dt);
    this.composer.render();
  };

  private updateAttract(dt: number) {
    const g = this.level.goal;
    const cx = (this.level.start.x + g.x) / 2, cz = (this.level.start.z + g.z) / 2;
    const r = Math.max(30, Math.hypot(g.x - this.level.start.x, g.z - this.level.start.z) * 0.75);
    const a = this.t * 0.06;
    this.camera.position.set(cx + Math.cos(a) * r, this.level.start.y + 14 + Math.sin(this.t * 0.2) * 3, cz + Math.sin(a) * r);
    this.camera.lookAt(cx, this.level.start.y, cz);
    this.pos.copy(this.level.start);
    this.player.root.position.copy(this.pos);
    animateAvatar(this.player, this.t, 0, false);
  }

  private updateAmbient(dt: number) {
    this.sky.position.copy(this.camera.position);
    (this.sky.material as THREE.ShaderMaterial).uniforms.time.value = this.t;
    for (const c of this.clouds) { c.position.x += dt * 1.2; if (c.position.x > 280) c.position.x -= 560; }
    this.motes.position.set(Math.round(this.camera.position.x / 50) * 50, 0, Math.round(this.camera.position.z / 50) * 50);
    this.motes.rotation.y = this.t * 0.01;
    this.sun.position.set(this.pos.x + 25, this.pos.y + 45, this.pos.z + 18);
    this.sun.target.position.copy(this.pos);
    (this.level.beacon.material as THREE.MeshBasicMaterial).opacity = (this.gateOpen ? 0.3 : 0.14) + Math.sin(this.t * 2) * 0.04;
  }

  private updatePlay(dt: number) {
    this.levelTime += dt;
    const inp = this.input;
    if (inp.consume('pause')) { this.ev.onPauseRequest(); return; }

    // camera look
    const look = inp.takeLook();
    this.yaw -= look.x * 0.0032; this.pitch = clamp(this.pitch + look.y * 0.0028, -0.25, 1.15);

    this.dashCd = Math.max(0, this.dashCd - dt); this.pulseCd = Math.max(0, this.pulseCd - dt);
    this.invuln = Math.max(0, this.invuln - dt);

    // movement intent relative to camera
    const ax = inp.axis();
    const fx = -Math.sin(this.yaw), fz = -Math.cos(this.yaw);
    const rx = Math.cos(this.yaw), rz = -Math.sin(this.yaw);
    let mx = fx * ax.y + rx * ax.x, mz = fz * ax.y + rz * ax.x;
    const mlen = Math.hypot(mx, mz);
    if (mlen > 0.01) { mx /= Math.max(1, mlen); mz /= Math.max(1, mlen); this.facing = Math.atan2(mx, mz) ; }

    // abilities
    if (inp.consume('jump')) this.tryJump();
    if (inp.consume('dash') && this.dashCd <= 0) {
      this.dashT = DASH_T; this.dashCd = DASH_CD;
      this.vel.x = Math.sin(this.facing) * DASH_V; this.vel.z = Math.cos(this.facing) * DASH_V;
      this.vel.y = Math.max(this.vel.y, 2);
      this.audio.dash();
      this.particles.emit(this.tmp.copy(this.pos).setY(this.pos.y + 0.9), 30, this.col.accent, 3, 0.5, 0.4);
    }
    if (inp.consume('pulse')) this.tryPulse();
    if (inp.consume('echo')) this.toggleEcho();
    if (inp.consume('dissolve')) this.dissolveEchoes();

    // integrate
    if (this.dashT > 0) {
      this.dashT -= dt;
      this.particles.emit(this.tmp.copy(this.pos).setY(this.pos.y + 0.9), 4, this.col.accent, 0.5, 0.35, 0.5);
    } else {
      const k = this.grounded ? 14 : 3.2;
      this.vel.x = damp(this.vel.x, mx * MOVE_SPEED, k, dt);
      this.vel.z = damp(this.vel.z, mz * MOVE_SPEED, k, dt);
    }
    this.vel.y -= GRAVITY * dt;
    if (this.grounded && this.ground) { this.pos.x += this.ground.dx; this.pos.y += this.ground.dy; this.pos.z += this.ground.dz; }
    const prevY = this.pos.y;
    this.pos.addScaledVector(this.vel, dt);
    this.collide(prevY);

    if (this.pos.y < this.level.goal.top - 45 && this.pos.y < this.level.start.y - 45) this.fellOff();

    // recording
    if (this.recording) {
      this.recT += dt;
      this.rec.push({ t: this.recT, x: this.pos.x, y: this.pos.y, z: this.pos.z, ry: this.player.root.rotation.y, sp: Math.hypot(this.vel.x, this.vel.z) / MOVE_SPEED });
      if (this.recT >= REC_MAX) this.toggleEcho();
    }

    // avatar
    this.player.root.position.copy(this.pos);
    let dr = this.facing - this.player.root.rotation.y; dr = Math.atan2(Math.sin(dr), Math.cos(dr));
    this.player.root.rotation.y += dr * Math.min(1, dt * 14);
    const sp01 = clamp(Math.hypot(this.vel.x, this.vel.z) / MOVE_SPEED, 0, 1);
    animateAvatar(this.player, this.t, sp01, !this.grounded);
    this.player.root.visible = this.invuln <= 0 || Math.floor(this.t * 20) % 2 === 0;
    if (sp01 > 0.5 && Math.random() < 0.5) this.particles.emit(this.tmp.copy(this.pos).setY(this.pos.y + 0.9), 1, this.col.accent, 0.4, 0.5, 0.18);

    this.updateEchoes(dt);
    this.updateShards();
    this.updatePads();
    this.updateHollows(dt);
    this.updateCamera(dt);

    // portal
    if (this.gateOpen && this.tmp.copy(this.pos).setY(this.pos.y + 1).distanceTo(this.level.portalPos) < 2.4) this.completeLevel();

    this.hudTimer -= dt;
    if (this.hudTimer <= 0) { this.hudTimer = 0.1; this.emitHud(); }
  }

  private tryJump() {
    const coyote = this.t - this.lastGroundT < 0.13;
    if (this.grounded || (coyote && this.jumps === 0)) {
      this.vel.y = JUMP_V; this.grounded = false; this.ground = null; this.jumps = 1; this.audio.jump();
    } else if (this.jumps < 2) {
      this.vel.y = DJUMP_V; this.jumps = 2; this.audio.doubleJump();
      this.particles.ring(this.tmp.copy(this.pos), 24, this.col.accent, 5, 0.4, 0.35);
    }
  }

  private collide(prevY: number) {
    const wasGrounded = this.grounded;
    this.grounded = false;
    let best: Platform | null = null;
    for (const p of this.level.platforms) {
      const inside = p.kind === 'cyl'
        ? Math.hypot(this.pos.x - p.x, this.pos.z - p.z) <= p.r - 0.05
        : Math.abs(this.pos.x - p.x) <= p.hx + 0.25 && Math.abs(this.pos.z - p.z) <= p.hz + 0.25;
      if (!inside) continue;
      if (this.vel.y <= 0 && this.pos.y <= p.top && prevY >= p.top - 0.35 - Math.abs(p.dy)) {
        if (!best || p.top > best.top) best = p;
      }
    }
    if (best) {
      this.pos.y = best.top; this.vel.y = 0; this.grounded = true; this.ground = best; this.jumps = 0;
      this.lastGroundT = this.t;
      if (!wasGrounded) { this.audio.land(); this.particles.ring(this.tmp.copy(this.pos).setY(this.pos.y + 0.05), 10, this.col.white, 2, 0.3, 0.25); }
      if (best.island) this.checkpoint.set(best.x, best.top, best.z);
    } else this.ground = null;
    // walls: island rims and obstacles
    for (const p of this.level.platforms) {
      if (p.kind !== 'cyl') continue;
      if (this.pos.y < p.top - 0.3 && this.pos.y > p.top - 2.2) {
        const dx = this.pos.x - p.x, dz = this.pos.z - p.z; const d = Math.hypot(dx, dz);
        if (d < p.r + 0.35 && d > 0.001) { const push = (p.r + 0.35) / d; this.pos.x = p.x + dx * push; this.pos.z = p.z + dz * push; }
      }
    }
    for (const o of this.level.obstacles) {
      if (o === this.level.sealObstacle && this.gateOpen) continue;
      if (this.pos.y + 1.6 < o.y0 || this.pos.y > o.y1) continue;
      const dx = this.pos.x - o.x, dz = this.pos.z - o.z; const d = Math.hypot(dx, dz); const min = o.r + 0.4;
      if (d < min && d > 0.001) { this.pos.x = o.x + (dx / d) * min; this.pos.z = o.z + (dz / d) * min; }
    }
  }

  private fellOff() {
    this.audio.fall();
    this.damage(1, false);
    if (this.mode !== 'playing') return;
    this.pos.copy(this.checkpoint).y += 2; this.vel.set(0, 0, 0);
    if (this.recording) { this.recording = false; this.rec = []; this.ev.onToast('Echo recording lost in the fall', 'bad'); }
    this.ev.onToast('The sky caught you. −1 vitality', 'bad');
  }

  private damage(n: number, knock = true, from?: THREE.Vector3) {
    if (this.invuln > 0 && knock) return;
    this.health -= n; this.invuln = 1.2; this.audio.hit();
    this.particles.emit(this.tmp.copy(this.pos).setY(this.pos.y + 1), 25, this.col.hollow, 6, 0.6, 0.35);
    if (knock && from) {
      const dx = this.pos.x - from.x, dz = this.pos.z - from.z; const d = Math.hypot(dx, dz) || 1;
      this.vel.set((dx / d) * 11, 7, (dz / d) * 11); this.grounded = false;
    }
    if (this.health <= 0) this.gameOver();
  }

  // ---------- Echoes: the signature mechanic ----------
  private toggleEcho() {
    if (!this.recording) {
      if (this.echoes.length >= this.level.padsNeeded) { this.audio.denied(); this.ev.onToast('Echo limit reached — press Q to dissolve echoes', 'bad'); return; }
      this.recording = true; this.recT = 0;
      this.rec = [{ t: 0, x: this.pos.x, y: this.pos.y, z: this.pos.z, ry: this.player.root.rotation.y, sp: 0 }];
      this.audio.recStart();
      this.particles.ring(this.tmp.copy(this.pos).setY(this.pos.y + 0.1), 40, this.col.accent2, 6, 0.6, 0.4);
      this.ev.onToast('Recording an Echo… move, then press E to release', 'info');
      return;
    }
    this.recording = false;
    if (this.rec.length < 5) { this.rec = []; return; }
    const avatar = buildAvatar(this.biome.accent2, true);
    const s0 = this.rec[0];
    avatar.root.position.set(s0.x, s0.y, s0.z);
    this.scene.add(avatar.root);
    this.echoes.push({ avatar, samples: this.rec, playT: 0, pos: new THREE.Vector3(s0.x, s0.y, s0.z), hp: 3, done: false, flash: 1 });
    this.rec = [];
    this.audio.recRelease();
    this.particles.emit(this.tmp.set(s0.x, s0.y + 1, s0.z), 50, this.col.accent2, 5, 0.8, 0.45);
    this.ev.onToast('Echo released — it replays your path and holds its final pose', 'good');
  }

  private dissolveEchoes() {
    if (!this.echoes.length && !this.recording) return;
    this.recording = false; this.rec = [];
    this.echoes.forEach((e) => { this.particles.emit(this.tmp.copy(e.pos).setY(e.pos.y + 1), 30, this.col.accent2, 4, 0.6, 0.4); this.scene.remove(e.avatar.root); });
    this.echoes = [];
    this.audio.echoBreak();
    this.ev.onToast('Echoes dissolved', 'info');
  }

  private updateEchoes(dt: number) {
    for (let i = this.echoes.length - 1; i >= 0; i--) {
      const e = this.echoes[i]; const S = e.samples; const end = S[S.length - 1].t;
      e.playT = Math.min(end, e.playT + dt);
      e.done = e.playT >= end;
      let j = 0; while (j < S.length - 2 && S[j + 1].t < e.playT) j++;
      const a = S[j], b = S[Math.min(j + 1, S.length - 1)];
      const k = b.t > a.t ? clamp((e.playT - a.t) / (b.t - a.t), 0, 1) : 1;
      e.pos.set(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k, a.z + (b.z - a.z) * k);
      e.avatar.root.position.copy(e.pos);
      e.avatar.root.rotation.y = b.ry;
      animateAvatar(e.avatar, this.t + i, e.done ? 0 : a.sp, false);
      e.flash = Math.max(0, e.flash - dt * 2);
      const op = 0.22 + e.flash * 0.5 + (e.hp < 3 ? Math.sin(this.t * 12) * 0.08 : 0);
      e.avatar.materials.forEach((m, mi) => { if (mi === 0) (m as THREE.MeshBasicMaterial).opacity = op; });
      if (Math.random() < 0.15) this.particles.emit(this.tmp.copy(e.pos).setY(e.pos.y + 0.9), 1, this.col.accent2, 0.6, 0.8, 0.2);
    }
  }

  // ---------- objectives ----------
  private updateShards() {
    const c = this.tmp.copy(this.pos).setY(this.pos.y + 0.9);
    for (const s of this.level.shards) {
      if (s.taken || c.distanceTo(s.mesh.position) > 1.35) continue;
      s.taken = true; s.mesh.visible = false; this.shardsGot++;
      this.score += 100;
      const got = this.level.shards.filter((x) => x.taken).length;
      this.audio.shard(got);
      this.particles.emit(s.mesh.position, 40, this.col.accent, 6, 0.9, 0.4, 4);
      if (got === this.level.shardsNeeded) this.ev.onToast('Enough shards! Reach the Skygate and power every Resonance Pad', 'good');
    }
  }

  private updatePads() {
    let active = 0;
    for (const p of this.level.pads) {
      const on = this.onPad(p.pos, this.pos) || this.echoes.some((e) => this.onPad(p.pos, e.pos));
      if (on !== p.active) this.audio.pad(on);
      p.active = on; if (on) active++;
    }
    this.padsActiveCount = active;
    const shardsOk = this.level.shards.filter((s) => s.taken).length >= this.level.shardsNeeded;
    if (!this.gateOpen && active === this.level.pads.length) {
      if (shardsOk) this.openGate();
      else if (!this.warnedShards) { this.warnedShards = true; this.audio.denied(); this.ev.onToast('The Seal resonates… but needs more Aether Shards', 'bad'); }
    }
    if (active < this.level.pads.length) this.warnedShards = false;
  }
  private onPad(pad: THREE.Vector3, p: THREE.Vector3) { return Math.hypot(p.x - pad.x, p.z - pad.z) < 1.35 && Math.abs(p.y - pad.y) < 1.2; }

  private openGate() {
    this.gateOpen = true; this.audio.gate();
    this.level.seal.visible = false; this.level.portal.visible = true;
    this.particles.emit(this.level.seal.position, 220, this.col.accent2, 14, 1.6, 0.6, 3, 3);
    this.score += 500;
    this.ev.onToast('THE SKYGATE IS OPEN — enter the portal!', 'good');
  }

  private completeLevel() {
    this.mode = 'transition'; this.input.enabled = false; this.input.exitLock();
    this.audio.portal();
    this.particles.emit(this.level.portalPos, 200, this.col.accent, 10, 1.4, 0.5);
    const bonus = 1000 * this.levelNum + Math.max(0, Math.round(3000 - this.levelTime * 15)) + this.health * 200;
    this.score += bonus;
    const stats = this.stats(bonus);
    setTimeout(() => this.ev.onLevelComplete(stats), 900);
  }

  private gameOver() {
    this.mode = 'over'; this.input.enabled = false; this.input.exitLock();
    this.audio.stopMusic();
    this.particles.emit(this.tmp.copy(this.pos).setY(this.pos.y + 1), 150, this.col.accent, 8, 1.5, 0.5);
    this.player.root.visible = false;
    const stats = this.stats(0);
    setTimeout(() => this.ev.onGameOver(stats), 1100);
  }

  private stats(bonus: number): RunStats {
    const newBest = this.score > this.best;
    if (newBest) { this.best = this.score; safeSet('aetherloop.best', String(this.best)); }
    return { level: this.levelNum, time: this.levelTime, shards: this.shardsGot, kills: this.kills, score: this.score, bonus, best: this.best, newBest };
  }

  // ---------- Hollows ----------
  private tryPulse() {
    if (this.pulseCd > 0) return;
    this.pulseCd = PULSE_CD; this.audio.pulse();
    const c = this.tmp.copy(this.pos).setY(this.pos.y + 0.9);
    this.particles.ring(c, 70, this.col.accent, PULSE_R * 2.6, 0.45, 0.6);
    this.particles.emit(c, 40, this.col.white, 5, 0.4, 0.3);
    for (let i = this.hollows.length - 1; i >= 0; i--) if (this.hollows[i].pos.distanceTo(c) < PULSE_R) this.killHollow(i);
  }

  private killHollow(i: number) {
    const h = this.hollows[i];
    this.particles.emit(h.pos, 45, this.col.hollow, 7, 0.8, 0.45, 2);
    this.scene.remove(h.group); this.hollows.splice(i, 1);
    this.kills++; this.score += 50; this.audio.kill();
  }

  private updateHollows(dt: number) {
    const L = this.levelNum;
    const maxAlive = 2 + L;
    const interval = Math.max(3, 9 - L * 0.6);
    for (const r of this.level.rifts) {
      r.mesh.rotation.z += dt * 0.5;
      if (r.pos.distanceTo(this.pos) > 55) continue;
      r.timer -= dt;
      if (r.timer <= 0 && this.hollows.length < maxAlive) {
        r.timer = interval;
        const { group, shell } = buildHollow(this.biome.hollow);
        const pos = r.pos.clone().setY(r.pos.y + 0.2);
        group.position.copy(pos); this.scene.add(group);
        this.hollows.push({ group, shell, pos, vel: new THREE.Vector3(0, 3, 0), home: r.pos.clone(), seed: Math.random() * 100, spawnT: this.t });
        this.particles.emit(pos, 30, this.col.hollow, 4, 0.7, 0.4);
      }
    }
    const speed = Math.min(6.5, 3.2 + L * 0.3);
    const pc = this.tmp.copy(this.pos).setY(this.pos.y + 0.9).clone();
    for (let i = this.hollows.length - 1; i >= 0; i--) {
      const h = this.hollows[i];
      // choose target: nearest of player and echoes
      let target: THREE.Vector3 | null = null; let tDist = 26; let echoTarget: Echo | null = null;
      const dp = h.pos.distanceTo(pc); if (dp < tDist) { tDist = dp; target = pc; }
      for (const e of this.echoes) {
        const ec = e.pos.clone().setY(e.pos.y + 0.9); const d = h.pos.distanceTo(ec);
        if (d < tDist) { tDist = d; target = ec; echoTarget = e; }
      }
      const desired = new THREE.Vector3();
      if (target) desired.subVectors(target, h.pos).normalize().multiplyScalar(speed);
      else {
        const th = this.t * 0.6 + h.seed;
        desired.set(h.home.x + Math.cos(th) * 3 - h.pos.x, h.home.y + 2.2 - h.pos.y, h.home.z + Math.sin(th) * 3 - h.pos.z).multiplyScalar(0.8);
      }
      desired.y += Math.sin(this.t * 3 + h.seed) * 0.8;
      h.vel.lerp(desired, 1 - Math.exp(-2.2 * dt));
      h.pos.addScaledVector(h.vel, dt);
      h.group.position.copy(h.pos);
      h.group.lookAt(target ?? this.tmp.copy(h.home).setY(h.home.y + 2));
      h.shell.rotation.x += dt * 1.5; h.shell.rotation.y += dt;
      const s = Math.min(1, (this.t - h.spawnT) * 2); h.group.scale.setScalar(s * (1 + Math.sin(this.t * 8 + h.seed) * 0.05));
      // contacts
      if (h.pos.distanceTo(pc) < 1.15) {
        if (this.dashT > 0) { this.killHollow(i); this.ev.onToast('Dash strike!', 'good'); continue; }
        this.damage(1, true, h.pos);
        h.vel.subVectors(h.pos, pc).normalize().multiplyScalar(9);
        if (this.mode !== 'playing') return;
      } else if (echoTarget && h.pos.distanceTo(target!) < 1.1) {
        echoTarget.hp--; echoTarget.flash = 1;
        this.particles.emit(h.pos, 30, this.col.accent2, 5, 0.6, 0.4);
        this.scene.remove(h.group); this.hollows.splice(i, 1);
        this.audio.echoBreak();
        if (echoTarget.hp <= 0) {
          this.scene.remove(echoTarget.avatar.root);
          this.echoes = this.echoes.filter((e) => e !== echoTarget);
          this.particles.emit(this.tmp.copy(echoTarget.pos).setY(echoTarget.pos.y + 1), 80, this.col.accent2, 8, 1, 0.5);
          this.ev.onToast('An Echo was shattered by the Hollows!', 'bad');
        }
      }
    }
  }

  // ---------- camera & HUD ----------
  private updateCamera(dt: number) {
    const target = this.tmp.copy(this.pos).setY(this.pos.y + 1.5);
    const cp = Math.cos(this.pitch);
    const desired = new THREE.Vector3(
      target.x + Math.sin(this.yaw) * cp * this.camDist,
      target.y + Math.sin(this.pitch) * this.camDist,
      target.z + Math.cos(this.yaw) * cp * this.camDist);
    this.camPos.x = damp(this.camPos.x, desired.x, 14, dt);
    this.camPos.y = damp(this.camPos.y, desired.y, 9, dt);
    this.camPos.z = damp(this.camPos.z, desired.z, 14, dt);
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(target);
    // hide trees that would block the view: near the camera or close to the camera→player line
    const cam = this.camPos; const seg = new THREE.Vector3().subVectors(target, cam); const segLen2 = seg.lengthSq() || 1;
    for (const o of this.level.occluders) {
      const c = this.tmp2.copy(o.position).setY(o.position.y + 2);
      const k = clamp(new THREE.Vector3().subVectors(c, cam).dot(seg) / segLen2, 0, 1);
      const closest = new THREE.Vector3().copy(cam).addScaledVector(seg, k);
      o.visible = c.distanceTo(cam) > 4 && !(k > 0.05 && k < 0.92 && closest.distanceTo(c) < 1.8);
    }
    const fovTarget = this.dashT > 0 ? 74 : 62;
    this.camera.fov = damp(this.camera.fov, fovTarget, 8, dt); this.camera.updateProjectionMatrix();
  }

  private emitHud(force = false) {
    if (!this.level) return;
    const shards = this.level.shards.filter((s) => s.taken).length;
    let objective: string; let target: THREE.Vector3;
    if (shards < this.level.shardsNeeded) {
      objective = `Collect Aether Shards (${shards}/${this.level.shardsNeeded})`;
      let best: THREE.Vector3 | null = null; let bd = Infinity;
      for (const s of this.level.shards) if (!s.taken) { const d = s.pos.distanceTo(this.pos); if (d < bd) { bd = d; best = s.pos; } }
      target = best ?? this.level.portalPos;
    } else if (!this.gateOpen) {
      objective = `Power all Resonance Pads at once (${this.padsActiveCount}/${this.level.pads.length}) — use Echoes [E]`;
      const free = this.level.pads.find((p) => !p.active);
      target = free ? free.pos : this.level.portalPos;
    } else { objective = 'Enter the Skygate portal'; target = this.level.portalPos; }
    const dx = target.x - this.pos.x, dz = target.z - this.pos.z;
    const worldAng = Math.atan2(dx, dz); const camAng = Math.atan2(-Math.sin(this.yaw), -Math.cos(this.yaw));
    void force;
    this.ev.onHud({
      level: this.levelNum, biome: this.biome.name, health: Math.max(0, this.health), maxHealth: MAX_HEALTH,
      shards, shardsNeeded: this.level.shardsNeeded, shardsTotal: this.level.shards.length,
      echoes: this.echoes.length, maxEchoes: this.level.padsNeeded, recording: this.recording, recordFrac: this.recT / REC_MAX,
      padsActive: this.padsActiveCount, padsNeeded: this.level.pads.length, gateOpen: this.gateOpen,
      score: this.score, time: this.levelTime, pulseCd: this.pulseCd / PULSE_CD, dashCd: this.dashCd / DASH_CD,
      objective, objAngle: camAng - worldAng, objDist: Math.hypot(dx, dz), best: this.best,
    });
  }
}

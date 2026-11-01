import * as THREE from 'three';
import type { Biome } from './biomes';

export function softTexture(size = 128, inner = 'rgba(255,255,255,1)', outer = 'rgba(255,255,255,0)') {
  const c = document.createElement('canvas'); c.width = c.height = size;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, inner); grad.addColorStop(1, outer);
  g.fillStyle = grad; g.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function cloudTexture() {
  const s = 256; const c = document.createElement('canvas'); c.width = c.height = s;
  const g = c.getContext('2d')!;
  for (let i = 0; i < 22; i++) {
    const x = s * (0.2 + Math.random() * 0.6), y = s * (0.35 + Math.random() * 0.3), r = s * (0.1 + Math.random() * 0.18);
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0, 'rgba(255,255,255,0.35)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function makeSky(b: Biome) {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: {
      top: { value: new THREE.Color(b.skyTop) }, horizon: { value: new THREE.Color(b.skyHorizon) },
      bottom: { value: new THREE.Color(b.skyBottom) }, aur1: { value: new THREE.Color(b.accent) },
      aur2: { value: new THREE.Color(b.accent2) }, time: { value: 0 },
    },
    vertexShader: `varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position.z = gl_Position.w; }`,
    fragmentShader: `
      uniform vec3 top, horizon, bottom, aur1, aur2; uniform float time; varying vec3 vDir;
      float hash(vec3 p){ p = fract(p*0.3183099+.1); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
      void main(){
        vec3 d = normalize(vDir); float h = d.y;
        vec3 col = h > 0.0 ? mix(horizon, top, pow(max(smoothstep(0.0, 0.75, h), 1e-4), 0.8)) : mix(horizon, bottom, smoothstep(0.0, -0.45, h));
        // stars
        vec3 cell = floor(d * 180.0); float s = hash(cell);
        float star = step(0.9965, s) * smoothstep(0.05, 0.4, h) * (0.6 + 0.4*sin(time*2.0 + s*90.0));
        col += vec3(star) * 1.4;
        // aurora ribbons
        float a = clamp(sin(d.x*4.0 + time*0.15 + sin(d.z*3.0 + time*0.1)*2.0) * 0.5 + 0.5, 0.0, 1.0);
        float band = smoothstep(0.15, 0.45, h) * smoothstep(0.9, 0.45, h);
        float rib = pow(a, 6.0) * band;
        col += mix(aur1, aur2, sin(d.z*2.0+time*0.2)*0.5+0.5) * rib * 0.55;
        gl_FragColor = vec4(max(col, vec3(0.0)), 1.0);
        #include <colorspace_fragment>
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(900, 48, 24), mat);
  mesh.renderOrder = -10; mesh.frustumCulled = false;
  return mesh;
}

/** Pooled GPU particle system — one draw call for every spark, trail and burst in the game. */
export class Particles {
  points: THREE.Points;
  private pos: Float32Array; private col: Float32Array; private size: Float32Array; private alpha: Float32Array;
  private vel: Float32Array; private life: Float32Array; private maxLife: Float32Array; private grav: Float32Array; private baseSize: Float32Array;
  private cursor = 0;
  constructor(private max = 2500) {
    this.pos = new Float32Array(max * 3); this.col = new Float32Array(max * 3); this.vel = new Float32Array(max * 3);
    this.size = new Float32Array(max); this.alpha = new Float32Array(max); this.life = new Float32Array(max);
    this.maxLife = new Float32Array(max); this.grav = new Float32Array(max); this.baseSize = new Float32Array(max);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('pcolor', new THREE.BufferAttribute(this.col, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('psize', new THREE.BufferAttribute(this.size, 1).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('palpha', new THREE.BufferAttribute(this.alpha, 1).setUsage(THREE.DynamicDrawUsage));
    const m = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { pr: { value: Math.min(window.devicePixelRatio, 1.5) } },
      vertexShader: `attribute float psize; attribute vec3 pcolor; attribute float palpha; uniform float pr;
        varying vec3 vC; varying float vA;
        void main(){ vC = pcolor; vA = palpha; vec4 mv = modelViewMatrix * vec4(position,1.0);
          gl_PointSize = psize * pr * (320.0 / max(0.1, -mv.z)); gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `varying vec3 vC; varying float vA;
        void main(){ float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard;
          float a = smoothstep(0.5, 0.0, d); gl_FragColor = vec4(vC * (1.0 + a * 1.5), a * vA); }`,
    });
    this.points = new THREE.Points(g, m);
    this.points.frustumCulled = false;
  }
  emit(p: THREE.Vector3, count: number, color: THREE.Color, speed = 4, life = 0.8, size = 0.35, gravity = 0, spread = 0.2) {
    for (let n = 0; n < count; n++) {
      const i = this.cursor; this.cursor = (this.cursor + 1) % this.max;
      this.pos[i * 3] = p.x + (Math.random() - 0.5) * spread;
      this.pos[i * 3 + 1] = p.y + (Math.random() - 0.5) * spread;
      this.pos[i * 3 + 2] = p.z + (Math.random() - 0.5) * spread;
      const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1), sp = speed * (0.4 + Math.random() * 0.6);
      this.vel[i * 3] = Math.sin(ph) * Math.cos(th) * sp;
      this.vel[i * 3 + 1] = Math.cos(ph) * sp;
      this.vel[i * 3 + 2] = Math.sin(ph) * Math.sin(th) * sp;
      this.col[i * 3] = color.r; this.col[i * 3 + 1] = color.g; this.col[i * 3 + 2] = color.b;
      this.life[i] = this.maxLife[i] = life * (0.6 + Math.random() * 0.4);
      this.grav[i] = gravity; this.baseSize[i] = size * (0.6 + Math.random() * 0.8);
    }
  }
  ring(p: THREE.Vector3, count: number, color: THREE.Color, speed: number, life = 0.6, size = 0.4) {
    for (let n = 0; n < count; n++) {
      const i = this.cursor; this.cursor = (this.cursor + 1) % this.max;
      const th = (n / count) * Math.PI * 2;
      this.pos[i * 3] = p.x; this.pos[i * 3 + 1] = p.y; this.pos[i * 3 + 2] = p.z;
      this.vel[i * 3] = Math.cos(th) * speed; this.vel[i * 3 + 1] = 0; this.vel[i * 3 + 2] = Math.sin(th) * speed;
      this.col[i * 3] = color.r; this.col[i * 3 + 1] = color.g; this.col[i * 3 + 2] = color.b;
      this.life[i] = this.maxLife[i] = life; this.grav[i] = 0; this.baseSize[i] = size;
    }
  }
  update(dt: number) {
    for (let i = 0; i < this.max; i++) {
      if (this.life[i] <= 0) { this.alpha[i] = 0; continue; }
      this.life[i] -= dt;
      const k = Math.max(0, this.life[i] / this.maxLife[i]);
      this.vel[i * 3 + 1] -= this.grav[i] * dt;
      const drag = Math.exp(-1.8 * dt);
      this.vel[i * 3] *= drag; this.vel[i * 3 + 1] *= drag; this.vel[i * 3 + 2] *= drag;
      this.pos[i * 3] += this.vel[i * 3] * dt; this.pos[i * 3 + 1] += this.vel[i * 3 + 1] * dt; this.pos[i * 3 + 2] += this.vel[i * 3 + 2] * dt;
      this.alpha[i] = k; this.size[i] = this.baseSize[i] * (0.4 + 0.6 * k);
    }
    const g = this.points.geometry;
    (['position', 'pcolor', 'psize', 'palpha'] as const).forEach((n) => { g.attributes[n].needsUpdate = true; });
  }
  clear() { this.life.fill(0); this.alpha.fill(0); }
}

export interface Avatar {
  root: THREE.Group; body: THREE.Group; halo: THREE.Mesh; core: THREE.Mesh; orbs: THREE.Mesh[];
  materials: THREE.Material[];
}

/** The Wayfarer — a luminous sky-walker. `ghost` builds the translucent Echo variant. */
export function buildAvatar(accent: string, ghost = false): Avatar {
  const root = new THREE.Group(); const body = new THREE.Group(); root.add(body);
  const acc = new THREE.Color(accent);
  const mats: THREE.Material[] = [];
  const solid = (color: string | THREE.Color, emissive?: THREE.Color, ei = 0) => {
    const m = ghost
      ? new THREE.MeshBasicMaterial({ color: emissive ?? acc, transparent: true, opacity: emissive ? 0.9 : 0.28, blending: THREE.AdditiveBlending, depthWrite: false })
      : new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.15, emissive: emissive ?? new THREE.Color(0), emissiveIntensity: ei });
    mats.push(m); return m;
  };
  const add = (geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number) => {
    const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = !ghost; body.add(m); return m;
  };
  const shell = solid('#eef1ff');
  add(new THREE.CapsuleGeometry(0.3, 0.62, 6, 14), shell, 0, 0.72, 0);
  add(new THREE.SphereGeometry(0.27, 24, 16), shell, 0, 1.42, 0);
  const visor = add(new THREE.SphereGeometry(0.2, 20, 12), solid('#111', acc, 4), 0, 1.44, 0.13);
  visor.scale.set(1.05, 0.45, 0.6);
  const core = add(new THREE.OctahedronGeometry(0.13), solid('#fff', acc, 5), 0, 0.9, 0.29);
  // shoulder fins
  const finMat = solid('#c9cff5', acc, ghost ? 0 : 0.6);
  for (const s of [-1, 1]) {
    const f = add(new THREE.ConeGeometry(0.1, 0.5, 4), finMat, 0.36 * s, 1.08, -0.08);
    f.rotation.z = -0.5 * s; f.rotation.x = -0.3;
  }
  const halo = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.025, 8, 48), solid('#fff', acc, 4));
  halo.position.y = 1.86; halo.rotation.x = Math.PI / 2; body.add(halo);
  const orbs: THREE.Mesh[] = [];
  const orbMat = solid('#fff', new THREE.Color(acc).offsetHSL(0.1, 0, 0), 5);
  for (let i = 0; i < 2; i++) { const o = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10, 8), orbMat); body.add(o); orbs.push(o); }
  return { root, body, halo, core, orbs, materials: mats };
}

export function animateAvatar(a: Avatar, t: number, speed01: number, airborne: boolean) {
  a.body.position.y = Math.sin(t * 9) * 0.05 * speed01 + (airborne ? 0.05 : 0);
  a.body.rotation.x = speed01 * 0.18;
  a.halo.rotation.z = t * 1.6;
  a.halo.position.y = 1.86 + Math.sin(t * 2.2) * 0.04;
  a.core.rotation.y = t * 3;
  a.orbs.forEach((o, i) => {
    const th = t * 2.4 + i * Math.PI;
    o.position.set(Math.cos(th) * 0.62, 1.1 + Math.sin(t * 3 + i) * 0.18, Math.sin(th) * 0.62);
  });
}

const hollowGeo = new THREE.IcosahedronGeometry(0.55, 0);
const hollowShell = new THREE.IcosahedronGeometry(0.8, 0);
const spikeGeo = new THREE.ConeGeometry(0.12, 0.55, 5);

export function buildHollow(color: string) {
  const g = new THREE.Group();
  const c = new THREE.Color(color);
  const core = new THREE.Mesh(hollowGeo, new THREE.MeshStandardMaterial({ color: '#07060c', roughness: 0.25, metalness: 0.9, emissive: c, emissiveIntensity: 0.25, flatShading: true }));
  core.castShadow = true; g.add(core);
  const shell = new THREE.Mesh(hollowShell, new THREE.MeshBasicMaterial({ color: c, wireframe: true, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending }));
  g.add(shell);
  const eye = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 10), new THREE.MeshStandardMaterial({ color: '#000', emissive: c, emissiveIntensity: 6 }));
  eye.position.z = 0.48; g.add(eye);
  const pos = hollowGeo.attributes.position;
  const seen = new Set<string>();
  for (let i = 0; i < pos.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pos, i);
    const key = v.toArray().map((n) => n.toFixed(2)).join();
    if (seen.has(key)) continue; seen.add(key);
    const s = new THREE.Mesh(spikeGeo, core.material);
    s.position.copy(v.clone().multiplyScalar(1.05));
    s.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.clone().normalize());
    g.add(s);
  }
  return { group: g, shell, eye };
}

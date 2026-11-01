import * as THREE from 'three';
import type { Biome } from './biomes';
import { mulberry32, range, type Rng } from './util';

export interface Platform {
  kind: 'cyl' | 'box';
  x: number; z: number; top: number;
  r: number; hx: number; hz: number;
  dx: number; dy: number; dz: number;
  island: boolean; index: number;
  mesh?: THREE.Object3D;
  mover?: { a: THREE.Vector3; b: THREE.Vector3; speed: number; phase: number };
}
export interface Obstacle { x: number; z: number; r: number; y0: number; y1: number }
export interface Shard { mesh: THREE.Mesh; pos: THREE.Vector3; baseY: number; taken: boolean; phase: number }
export interface Pad { pos: THREE.Vector3; ring: THREE.Mesh; column: THREE.Mesh; active: boolean; glow: number }
export interface Rift { pos: THREE.Vector3; mesh: THREE.Mesh; timer: number }

const swirlVert = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`;
const swirlFrag = `uniform float time; uniform vec3 c1; uniform vec3 c2; uniform float dark; varying vec2 vUv;
  void main(){ vec2 p = vUv - 0.5; float r = length(p) * 2.0; if (r > 1.0) discard;
    float a = atan(p.y, p.x); float s = sin(a * 5.0 + r * 14.0 - time * 3.0) * 0.5 + 0.5;
    vec3 col = mix(c1, c2, s) * (1.6 - r) ; float alpha = smoothstep(1.0, 0.75, r);
    col = mix(col, vec3(0.02,0.0,0.05) * (1.0 - s * 0.5), dark);
    gl_FragColor = vec4(col * (1.0 + (1.0 - r) * 2.0 * (1.0 - dark)), alpha * mix(0.95, 0.9, dark)); }`;

export class Level {
  group = new THREE.Group();
  platforms: Platform[] = [];
  obstacles: Obstacle[] = [];
  shards: Shard[] = [];
  pads: Pad[] = [];
  rifts: Rift[] = [];
  islands: Platform[] = [];
  /** Tall decorations that get hidden when they come between the camera and the player. */
  occluders: THREE.Object3D[] = [];
  shardsNeeded = 0;
  padsNeeded: number;
  start = new THREE.Vector3();
  goal!: Platform;
  portal!: THREE.Group;
  portalPos = new THREE.Vector3();
  seal!: THREE.Group;
  beacon!: THREE.Mesh;
  sealObstacle!: Obstacle;
  private swirls: THREE.ShaderMaterial[] = [];
  private floaters: { m: THREE.Object3D; cx: number; cz: number; r: number; th: number; sp: number; y: number }[] = [];
  private rng: Rng;
  private accent: THREE.Color;
  private accent2: THREE.Color;

  constructor(public level: number, public biome: Biome, seed: number) {
    this.rng = mulberry32(seed);
    this.accent = new THREE.Color(biome.accent);
    this.accent2 = new THREE.Color(biome.accent2);
    this.padsNeeded = level >= 6 ? 4 : level >= 3 ? 3 : 2;
    this.generate();
  }

  private generate() {
    const rng = this.rng; const L = this.level;
    const start = this.addIsland(0, 0, 0, 7.5, 0);
    const path: Platform[] = [start];
    let angle = rng() * Math.PI * 2;
    const count = 5 + Math.min(L, 6);
    for (let i = 1; i <= count; i++) {
      const prev = path[i - 1]; const last = i === count;
      const r = last ? 12 : range(rng, 4, 7.5);
      const useMover = !last && i > 1 && rng() < 0.22 + Math.min(L, 8) * 0.04;
      const gap = useMover ? range(rng, 9, 12.5) : range(rng, 2.5, 5) + Math.min(L * 0.2, 1.2);
      let dy = useMover ? range(rng, -2, 3) : Math.min(1.6, range(rng, -2.2, 1.8));
      let x = 0, z = 0;
      for (let tries = 0; tries < 10; tries++) {
        const a = angle + (rng() - 0.5) * 1.3 + (tries > 0 ? tries * 0.6 * (tries % 2 ? 1 : -1) : 0);
        const dist = prev.r + r + gap;
        x = prev.x + Math.cos(a) * dist; z = prev.z + Math.sin(a) * dist;
        if (this.islands.every((o) => o === prev || Math.hypot(o.x - x, o.z - z) > o.r + r + 3)) { angle = a; break; }
      }
      const isl = this.addIsland(x, prev.top + dy, z, r, i);
      if (useMover) this.addMover(prev, isl);
      path.push(isl);
    }
    this.goal = path[path.length - 1];
    // side islands for exploration (with bonus shards)
    const sides = 1 + Math.floor(L / 2);
    for (let s = 0; s < sides; s++) {
      const host = path[1 + Math.floor(rng() * (path.length - 2))];
      const r = range(rng, 3, 4.5);
      for (let tries = 0; tries < 8; tries++) {
        const a = rng() * Math.PI * 2; const dist = host.r + r + range(rng, 2.5, 4.5);
        const x = host.x + Math.cos(a) * dist, z = host.z + Math.sin(a) * dist;
        if (this.islands.every((o) => Math.hypot(o.x - x, o.z - z) > o.r + r + 2.5)) {
          const isl = this.addIsland(x, host.top + range(rng, -1, 1.5), z, r, -1);
          this.addShard(isl, true); this.addShard(isl, false);
          break;
        }
      }
    }
    // shards along the path
    for (let i = 1; i < path.length - 1; i++) {
      this.addShard(path[i], rng() < 0.35);
      if (path[i].r > 5.5 && rng() < 0.6) this.addShard(path[i], rng() < 0.5);
    }
    this.shardsNeeded = Math.max(3, this.shards.length - Math.floor(this.shards.length / 4));
    // rifts — sources of Hollows
    for (let i = 2; i < path.length - 1; i++) if (rng() < 0.3 + L * 0.05) this.addRift(path[i]);
    if (L >= 2) this.addRift(this.goal, true);
    this.buildGoal();
    this.decorateAll();
    this.addBackground();
    this.start.set(start.x, start.top, start.z);
  }

  private addIsland(x: number, y: number, z: number, r: number, index: number) {
    const b = this.biome; const rng = this.rng;
    const p: Platform = { kind: 'cyl', x, z, top: y, r, hx: 0, hz: 0, dx: 0, dy: 0, dz: 0, island: true, index };
    const g = new THREE.Group(); g.position.set(x, y, z);
    const seg = Math.max(12, Math.round(r * 2.6));
    const grassGeo = new THREE.CylinderGeometry(r, r * 0.94, 0.9, seg, 1);
    const grass = new THREE.Mesh(grassGeo, new THREE.MeshStandardMaterial({ color: b.grass, roughness: 0.85, flatShading: true }));
    grass.position.y = -0.45; grass.receiveShadow = true; g.add(grass);
    const depth = r * range(rng, 1.3, 2.1);
    const cone = new THREE.ConeGeometry(r * 0.95, depth, seg, 5);
    const s1 = rng() * 10, s2 = rng() * 10;
    const pa = cone.attributes.position; const colors: number[] = [];
    const rock = new THREE.Color(b.rock); const dark = rock.clone().multiplyScalar(0.35);
    for (let i = 0; i < pa.count; i++) {
      const vx = pa.getX(i), vy = pa.getY(i), vz = pa.getZ(i);
      // cone is flipped later: base (h=0) meets the grass, tip (h=1) hangs below
      const h = Math.min(1, Math.max(0, (vy + depth / 2) / depth));
      const th = Math.atan2(vz, vx);
      const n = 1 + 0.16 * Math.sin(th * 3 + s1) * Math.sin(vy * 1.3 + s2) + 0.1 * Math.sin(th * 7 + s2);
      const k = h < 0.01 ? 1 : n;
      pa.setX(i, vx * k); pa.setZ(i, vz * k);
      const c = dark.clone().lerp(rock, Math.pow(1 - h, 0.7)); colors.push(c.r, c.g, c.b);
    }
    cone.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    cone.computeVertexNormals();
    const under = new THREE.Mesh(cone, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, flatShading: true }));
    under.rotation.x = Math.PI; under.position.y = -0.9 - depth / 2 + 0.01; under.castShadow = true; under.receiveShadow = true;
    g.add(under);
    // glowing veins on the underside
    const veinMat = new THREE.MeshBasicMaterial({ color: this.accent2, transparent: true, opacity: 0.8 });
    for (let v = 0; v < Math.round(r); v++) {
      const th = rng() * Math.PI * 2; const hh = range(rng, 0.2, 0.7);
      const vein = new THREE.Mesh(new THREE.OctahedronGeometry(0.18 + rng() * 0.2), veinMat);
      const rad = r * 0.95 * (1 - hh) * 0.98;
      vein.position.set(Math.cos(th) * rad, -0.9 - depth * hh, Math.sin(th) * rad);
      g.add(vein);
    }
    p.mesh = g; this.group.add(g);
    this.platforms.push(p); this.islands.push(p);
    // orbiting pebbles
    for (let k = 0; k < Math.round(r * 0.5); k++) {
      const m = new THREE.Mesh(new THREE.DodecahedronGeometry(range(rng, 0.2, 0.55), 0), new THREE.MeshStandardMaterial({ color: b.rock, flatShading: true, roughness: 0.9 }));
      m.castShadow = true; this.group.add(m);
      this.floaters.push({ m, cx: x, cz: z, r: r + range(rng, 1.5, 4), th: rng() * 6.28, sp: range(rng, 0.05, 0.2) * (rng() < 0.5 ? -1 : 1), y: y - range(rng, 1, 4) });
    }
    return p;
  }

  private addMover(a: Platform, b: Platform) {
    const dir = new THREE.Vector3(b.x - a.x, 0, b.z - a.z).normalize();
    const hx = 1.7;
    const A = new THREE.Vector3(a.x, a.top, a.z).addScaledVector(dir, a.r + hx + 0.2);
    const B = new THREE.Vector3(b.x, b.top, b.z).addScaledVector(dir, -(b.r + hx + 0.2));
    const dist = A.distanceTo(B);
    const p: Platform = { kind: 'box', x: A.x, z: A.z, top: A.y, r: 0, hx, hz: hx, dx: 0, dy: 0, dz: 0, island: false, index: -2,
      mover: { a: A, b: B, speed: (Math.PI * 3.0) / Math.max(dist, 2), phase: this.rng() * 6 } };
    const g = new THREE.Group();
    const slab = new THREE.Mesh(new THREE.BoxGeometry(hx * 2, 0.5, hx * 2), new THREE.MeshStandardMaterial({ color: this.biome.rock, roughness: 0.4, metalness: 0.6 }));
    slab.position.y = -0.25; slab.castShadow = true; slab.receiveShadow = true; g.add(slab);
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(slab.geometry), new THREE.LineBasicMaterial({ color: this.accent }));
    edge.position.y = -0.25; g.add(edge);
    const jet = new THREE.Mesh(new THREE.SphereGeometry(0.4, 12, 8), new THREE.MeshBasicMaterial({ color: this.accent }));
    jet.position.y = -0.7; jet.scale.y = 0.4; g.add(jet);
    p.mesh = g; this.group.add(g); this.platforms.push(p);
  }

  private addShard(isl: Platform, high: boolean) {
    const rng = this.rng;
    const a = rng() * Math.PI * 2, d = rng() * (isl.r - 1.5);
    const y = isl.top + (high ? range(rng, 2.6, 3.6) : 1.1);
    const mesh = new THREE.Mesh(new THREE.OctahedronGeometry(0.38), new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: this.accent, emissiveIntensity: 3.5, roughness: 0.1, metalness: 0.4 }));
    mesh.scale.set(0.7, 1.25, 0.7);
    const pos = new THREE.Vector3(isl.x + Math.cos(a) * d, y, isl.z + Math.sin(a) * d);
    mesh.position.copy(pos); this.group.add(mesh);
    this.shards.push({ mesh, pos, baseY: y, taken: false, phase: rng() * 6 });
  }

  private addRift(isl: Platform, nearEdge = false) {
    const a = this.rng() * Math.PI * 2, d = nearEdge ? isl.r - 2.2 : this.rng() * (isl.r - 2.5);
    const pos = new THREE.Vector3(isl.x + Math.cos(a) * d, isl.top + 0.03, isl.z + Math.sin(a) * d);
    const mat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { time: { value: 0 }, c1: { value: new THREE.Color(this.biome.hollow) }, c2: { value: new THREE.Color('#000') }, dark: { value: 0.65 } },
      vertexShader: swirlVert, fragmentShader: swirlFrag });
    this.swirls.push(mat);
    const mesh = new THREE.Mesh(new THREE.CircleGeometry(1.5, 40), mat);
    mesh.rotation.x = -Math.PI / 2; mesh.position.copy(pos); this.group.add(mesh);
    this.rifts.push({ pos, mesh, timer: 2 + this.rng() * 4 });
  }

  private buildGoal() {
    const g = this.goal; const b = this.biome;
    const center = new THREE.Vector3(g.x, g.top, g.z);
    // Resonance Pads around the Skygate
    const n = this.padsNeeded; const off = this.rng() * Math.PI * 2;
    for (let i = 0; i < n; i++) {
      const a = off + (i / n) * Math.PI * 2; const rad = 7.6;
      const pos = new THREE.Vector3(g.x + Math.cos(a) * rad, g.top, g.z + Math.sin(a) * rad);
      const base = new THREE.Mesh(new THREE.CylinderGeometry(1.25, 1.4, 0.18, 32), new THREE.MeshStandardMaterial({ color: '#1a1a2a', roughness: 0.3, metalness: 0.8 }));
      base.position.copy(pos).y += 0.09; base.receiveShadow = true; this.group.add(base);
      const ring = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.07, 10, 48), new THREE.MeshStandardMaterial({ color: '#fff', emissive: this.accent2, emissiveIntensity: 0.6 }));
      ring.rotation.x = Math.PI / 2; ring.position.copy(pos).y += 0.2; this.group.add(ring);
      const column = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.1, 5, 32, 1, true), new THREE.MeshBasicMaterial({ color: this.accent2, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
      column.position.copy(pos).y += 2.5; this.group.add(column);
      this.pads.push({ pos, ring, column, active: false, glow: 0 });
    }
    // Skygate arch
    const stone = new THREE.MeshStandardMaterial({ color: b.rock, roughness: 0.6, metalness: 0.3, flatShading: true });
    const trim = new THREE.MeshStandardMaterial({ color: '#fff', emissive: this.accent, emissiveIntensity: 2 });
    for (const s of [-1, 1]) {
      const pillar = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.6, 5.2, 6), stone);
      pillar.position.set(g.x + s * 2.9, g.top + 2.6, g.z); pillar.castShadow = true; this.group.add(pillar);
      const cap = new THREE.Mesh(new THREE.OctahedronGeometry(0.45), trim);
      cap.position.set(g.x + s * 2.9, g.top + 5.7, g.z); this.group.add(cap);
      this.obstacles.push({ x: g.x + s * 2.9, z: g.z, r: 0.6, y0: g.top, y1: g.top + 5.2 });
    }
    const lintel = new THREE.Mesh(new THREE.TorusGeometry(2.9, 0.22, 8, 40, Math.PI), stone);
    lintel.position.set(g.x, g.top + 5.2, g.z); this.group.add(lintel);
    this.portal = new THREE.Group(); this.portal.position.set(g.x, g.top + 2.4, g.z);
    const pmat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { time: { value: 0 }, c1: { value: this.accent.clone() }, c2: { value: this.accent2.clone() }, dark: { value: 0 } },
      vertexShader: swirlVert, fragmentShader: swirlFrag });
    this.swirls.push(pmat);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(2.2, 48), pmat);
    this.portal.add(disc);
    const pring = new THREE.Mesh(new THREE.TorusGeometry(2.25, 0.1, 10, 64), trim);
    this.portal.add(pring);
    this.portal.visible = false; this.group.add(this.portal);
    this.portalPos.copy(this.portal.position);
    // The Seal — a crystalline shell guarding the gate
    this.seal = new THREE.Group(); this.seal.position.copy(center).y += 2.4;
    const shell = new THREE.Mesh(new THREE.IcosahedronGeometry(3.4, 1), new THREE.MeshBasicMaterial({ color: this.accent2, transparent: true, opacity: 0.12, blending: THREE.AdditiveBlending, depthWrite: false }));
    const wire = new THREE.Mesh(new THREE.IcosahedronGeometry(3.45, 1), new THREE.MeshBasicMaterial({ color: this.accent2, wireframe: true, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending }));
    this.seal.add(shell, wire); this.group.add(this.seal);
    this.sealObstacle = { x: g.x, z: g.z, r: 3.4, y0: g.top - 1, y1: g.top + 5.8 };
    this.obstacles.push(this.sealObstacle);
    // Beacon of light, visible across the sky
    this.beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 260, 16, 1, true), new THREE.MeshBasicMaterial({ color: this.accent2, transparent: true, opacity: 0.16, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }));
    this.beacon.position.set(g.x, g.top + 130, g.z); this.group.add(this.beacon);
  }

  private decorateAll() {
    const b = this.biome; const rng = this.rng;
    const trunkMat = new THREE.MeshStandardMaterial({ color: b.trunk, roughness: 0.9, flatShading: true });
    const leafMat = new THREE.MeshStandardMaterial({ color: b.foliage, roughness: 0.7, flatShading: true });
    const leafMat2 = new THREE.MeshStandardMaterial({ color: new THREE.Color(b.foliage).offsetHSL(0.04, 0, 0.08), roughness: 0.7, flatShading: true });
    const crystalMat = new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: this.accent2, emissiveIntensity: 1.6, roughness: 0.1, metalness: 0.2, flatShading: true });
    const grassMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(b.grass).offsetHSL(0, 0.05, 0.08), flatShading: true });
    const occupied: { x: number; z: number; r: number }[] = [
      ...this.pads.map((p) => ({ x: p.pos.x, z: p.pos.z, r: 2 })),
      ...this.rifts.map((p) => ({ x: p.pos.x, z: p.pos.z, r: 2 })),
      { x: this.goal.x, z: this.goal.z, r: 4.5 },
      { x: this.islands[0].x, z: this.islands[0].z, r: 2 },
    ];
    const free = (x: number, z: number, r: number) => occupied.every((o) => Math.hypot(o.x - x, o.z - z) > o.r + r);
    for (const isl of this.islands) {
      const nTrees = Math.floor(isl.r * 0.5 + rng() * 2);
      for (let i = 0; i < nTrees; i++) {
        const a = rng() * 6.28, d = range(rng, 1, isl.r - 1.3); const x = isl.x + Math.cos(a) * d, z = isl.z + Math.sin(a) * d;
        if (!free(x, z, 1.2)) continue;
        occupied.push({ x, z, r: 1.2 });
        const h = range(rng, 1.8, 3.4);
        const t = new THREE.Group(); t.position.set(x, isl.top, z);
        const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.24, h, 6), trunkMat); trunk.position.y = h / 2; trunk.castShadow = true; t.add(trunk);
        const blobs = 2 + Math.floor(rng() * 2);
        for (let k = 0; k < blobs; k++) {
          const leaf = new THREE.Mesh(new THREE.IcosahedronGeometry(range(rng, 0.7, 1.2), 0), k % 2 ? leafMat2 : leafMat);
          leaf.position.set(range(rng, -0.5, 0.5), h + range(rng, -0.2, 0.7), range(rng, -0.5, 0.5)); leaf.castShadow = true; t.add(leaf);
        }
        t.rotation.y = rng() * 6.28; this.group.add(t); this.occluders.push(t);
        this.obstacles.push({ x, z, r: 0.35, y0: isl.top, y1: isl.top + h });
      }
      const nCrys = rng() < 0.6 ? 1 + Math.floor(rng() * 2) : 0;
      for (let i = 0; i < nCrys; i++) {
        const a = rng() * 6.28, d = range(rng, 1, isl.r - 1); const x = isl.x + Math.cos(a) * d, z = isl.z + Math.sin(a) * d;
        if (!free(x, z, 0.9)) continue;
        occupied.push({ x, z, r: 0.9 });
        for (let k = 0; k < 4; k++) {
          const c = new THREE.Mesh(new THREE.OctahedronGeometry(0.3), crystalMat);
          const hh = range(rng, 0.8, 2.2); c.scale.set(0.8, hh * 1.6, 0.8);
          c.position.set(x + range(rng, -0.4, 0.4), isl.top + hh * 0.35, z + range(rng, -0.4, 0.4));
          c.rotation.set(range(rng, -0.35, 0.35), rng() * 3, range(rng, -0.35, 0.35)); this.group.add(c);
        }
        this.obstacles.push({ x, z, r: 0.6, y0: isl.top, y1: isl.top + 2 });
      }
      for (let i = 0; i < isl.r * 2; i++) {
        const a = rng() * 6.28, d = rng() * (isl.r - 0.4);
        const tuft = new THREE.Mesh(new THREE.ConeGeometry(0.08, range(rng, 0.25, 0.5), 3), grassMat);
        tuft.position.set(isl.x + Math.cos(a) * d, isl.top + 0.15, isl.z + Math.sin(a) * d); this.group.add(tuft);
      }
    }
  }

  private addBackground() {
    const rng = this.rng; const mat = new THREE.MeshStandardMaterial({ color: this.biome.rock, flatShading: true, roughness: 1 });
    for (let i = 0; i < 9; i++) {
      const a = rng() * 6.28, d = range(rng, 170, 300), s = range(rng, 18, 45);
      const m = new THREE.Mesh(new THREE.ConeGeometry(s, s * 2.2, 7), mat);
      m.rotation.x = Math.PI; m.position.set(Math.cos(a) * d, range(rng, -30, 40), Math.sin(a) * d); this.group.add(m);
      const top = new THREE.Mesh(new THREE.CylinderGeometry(s, s * 0.95, 3, 7), new THREE.MeshStandardMaterial({ color: this.biome.grass, flatShading: true }));
      top.position.copy(m.position).y += s * 1.1 + 1.5; this.group.add(top);
    }
  }

  update(t: number, dt: number) {
    for (const p of this.platforms) {
      if (!p.mover) continue;
      const s = 0.5 - 0.5 * Math.cos(t * p.mover.speed + p.mover.phase);
      const nx = p.mover.a.x + (p.mover.b.x - p.mover.a.x) * s;
      const ny = p.mover.a.y + (p.mover.b.y - p.mover.a.y) * s;
      const nz = p.mover.a.z + (p.mover.b.z - p.mover.a.z) * s;
      p.dx = nx - p.x; p.dy = ny - p.top; p.dz = nz - p.z;
      p.x = nx; p.top = ny; p.z = nz;
      p.mesh!.position.set(nx, ny, nz);
    }
    for (const s of this.shards) {
      if (s.taken) continue;
      s.mesh.rotation.y = t * 1.8 + s.phase;
      s.mesh.position.y = s.baseY + Math.sin(t * 2 + s.phase) * 0.18;
    }
    for (const f of this.floaters) {
      f.th += f.sp * dt;
      f.m.position.set(f.cx + Math.cos(f.th) * f.r, f.y + Math.sin(t * 0.6 + f.r) * 0.4, f.cz + Math.sin(f.th) * f.r);
      f.m.rotation.x += dt * 0.2; f.m.rotation.y += dt * 0.15;
    }
    for (const m of this.swirls) m.uniforms.time.value = t;
    for (const p of this.pads) {
      p.glow += ((p.active ? 1 : 0) - p.glow) * Math.min(1, dt * 6);
      (p.ring.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.6 + p.glow * 4 + Math.sin(t * 3) * 0.2;
      (p.column.material as THREE.MeshBasicMaterial).opacity = p.glow * 0.22;
      p.ring.rotation.z = t * (0.3 + p.glow * 2);
    }
    this.seal.rotation.y = t * 0.2; this.seal.rotation.x = Math.sin(t * 0.3) * 0.1;
    this.portal.rotation.y = Math.sin(t * 0.5) * 0.15;
  }

  dispose() {
    this.group.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.geometry) m.geometry.dispose();
      const mat = m.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose();
    });
    this.group.removeFromParent();
  }
}

# Aetherloop

**A 3D sky-island adventure where your most powerful ally is yourself — a few seconds ago.**

Your Wayfarer explores floating islands looking for Aether Shards. Every Skygate is sealed by Resonance Pads that must all be powered **at the same time**, and they're too far apart for one person to hold. So you record an **Echo**: press `E`, move, press `E` again. A ghost of you replays that exact path, then stays where it stopped and keeps holding the pad. Meanwhile the **Hollows** come out of rifts and go after you *and* your Echoes. Three hits break an Echo.

## Play locally

```bash
cd aetherloop
npm install
npm run dev        # http://localhost:8080
npm run build      # production bundle in dist/
```

## Controls

| Action | Keyboard / mouse | Touch |
|---|---|---|
| Move | WASD / arrows | Left-side stick |
| Camera | Mouse (click to capture) | Drag on the right side |
| Jump / double jump | Space | JUMP |
| Dash (destroys Hollows on contact) | Shift | DASH |
| Record / release Echo | E | ECHO |
| Pulse (area blast) | F or left click | PULSE |
| Dissolve all Echoes | Q | Q |
| Pause | Esc / P | ❚❚ |

## Features

- **Echo mechanic.** Your recorded movement plays back as an AI-free co-op partner. You can have as many Echoes as there are pads, and they can be destroyed, so a puzzle can turn into a fight.
- **Endless procedural campaign.** Each level gets a seeded archipelago with jump gaps, moving platforms, side islands with bonus shards, rifts, and a final Skygate island. Difficulty goes up with every level: more pads, more Hollows, faster enemies.
- **Five biomes:** Aurora Reach, Ember Atoll, Verdant Drift, Abyssal Bloom and Solar Choir. Each has its own sky shader, fog, palette, enemy colour and music key.
- **Rendering:** HDR bloom, ACES tone mapping, soft shadows, a GPU particle system in one draw call, a shader sky with aurora and stars, and volumetric-style cloud sprites.
- **Synthesized audio.** The score and every sound effect are generated live with WebAudio, so the game uses no licensed assets.
- **Polish:** coyote time, double jump, dash FOV kick, a camera that hides trees blocking the view, an objective compass, best-score saving, a graphics quality toggle, look sensitivity, mute, and full touch controls.

## Tech

React 18 + TypeScript + Vite + Three.js (r160). This is Lovable's native stack, so the folder can be connected to a Lovable project through GitHub. All 3D assets are built in code. There are no external models, textures or audio files.

## Code map

| File | Responsibility |
|---|---|
| `src/game/engine.ts` | Game loop, physics, Echo recording/playback, Hollow AI, combat, camera, HUD feed |
| `src/game/world.ts` | Procedural level generation (islands, movers, shards, pads, Skygate, rifts, decoration) |
| `src/game/fx.ts` | Sky shader, particle system, Wayfarer/Echo avatar, Hollow models |
| `src/game/audio.ts` | Procedural music and SFX |
| `src/game/input.ts` | Keyboard, mouse/pointer-lock, and touch input |
| `src/game/biomes.ts` | Biome palettes |
| `src/App.tsx` | Menus, HUD, settings, results screens |

See [GAME_DESIGN.md](./GAME_DESIGN.md) for the design rationale, business model, legal notes and roadmap.

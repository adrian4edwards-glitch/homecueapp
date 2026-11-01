# Aetherloop: Design and Strategy Brief

## 1. The one-sentence pitch
*A sky-island adventure where you solve puzzles and survive fights by teaming up with recordings of yourself.*

## 2. Why it's different
Most big action games give you **more power**: bigger guns, more cars, more blocks. Aetherloop gives you **more of yourself**. Every Echo is a plan you acted out ahead of time, so the puzzles reward thinking ahead, and the Hollows, which hunt your Echoes too, turn those plans into something you have to defend. The core loop is plan → record → defend → resonate. Players can share it as clips ("watch my three Echoes hold the gate"), and the same loop works for multiplayer later.

## 3. Core loop (shipped in this build)
1. **Explore.** Cross a procedurally generated archipelago using jumps, double jumps, dashes and moving platforms.
2. **Gather.** Collect enough Aether Shards (about 75%) to tune the Seal.
3. **Plan.** Count the Resonance Pads (2 → 3 → 4 as you progress). Record Echoes that walk to each pad.
4. **Defend.** Hollows spawn from rifts and go for the closest target. Pulse (`F`) or dash through them. Three hits break an Echo.
5. **Resonate.** When every pad is powered at once, the Seal breaks and the portal opens. Score bonuses reward speed and health left.

## 4. Pillars
- **Clarity:** one new verb (Echo) that can be learned in ten seconds and takes a long time to master.
- **Readability:** strong silhouettes, emissive cues for anything interactive, and a beam of light marking every goal.
- **Fairness:** coyote time, a double jump, checkpoints on every island, and falls that cost 1 vitality instead of a restart.
- **Zero-asset pipeline:** every mesh, shader and sound is code, so the game is small, loads fast and has no asset licensing risk.

## 5. Roadmap
| Phase | Features |
|---|---|
| **v1 (this build)** | Single-player endless campaign, 5 biomes, Echoes, Hollows, touch + desktop |
| **v1.5** | Daily seeded "Skyrun" with a global leaderboard (Lovable Cloud / Postgres), ghost replays of top runs |
| **v2** | **Async Echoes:** your recorded Echoes appear in friends' worlds as helpers. Level editor and shareable seeds |
| **v3** | Real-time 2–4 player co-op where every player also has Echoes. Boss Hollows. Cosmetic Wayfarer skins and halo trails |
| **v4** | Creator platform: user-made archipelagos, a curated featured feed, revenue share for creators |

## 6. Business model (ethical, no pay-to-win)
- Free-to-play web, mobile web, and later native wrappers.
- **Cosmetics:** avatar skins, halo and trail effects, Echo colours, island themes.
- **Season pass** with new biome drops and cosmetic tracks. Gameplay content stays free.
- **Creator economy** (v4): a revenue share on cosmetic sales tied to popular user levels.
- KPIs: D1/D7/D30 retention, sessions per day, share rate of Echo clips, ARPDAU, creator level plays.
- Valuation is never guaranteed. Success depends on retention, community and execution, so the roadmap tests the core loop with real players before scaling.

## 7. Legal and IP checklist
- **Original work.** The name, characters (Wayfarer, Echoes, Hollows), world, code, shaders, models and music are all original and generated in this repository. No third-party assets are included.
- **Game mechanics** aren't protected by copyright, but specific expression is. Aetherloop's look, story and implementation are its own.
- **Before commercial launch:** run a USPTO/EUIPO/WIPO trademark clearance search on "Aetherloop", reserve the domain and social handles, and file trademarks in your target classes (9 and 41).
- **Fonts:** Orbitron and Inter under the SIL Open Font License, loaded from Google Fonts.
- **Libraries:** React and Vite (MIT), Three.js (MIT). Keep license notices in distributions.
- **Before adding accounts or leaderboards:** privacy policy, terms of service, COPPA/GDPR-K age gating for under-13s, and moderation for user-generated content (v2+).
- Have a qualified attorney review all of the above. This is a checklist, not legal advice.

## 8. Technical architecture
- **Client:** React (UI shell) + Three.js (renderer) + a fixed-function game loop with a 50 ms delta clamp.
- **World generation:** a deterministic seeded generator (`mulberry32`) per level. The same seed gives the same world, which is ready for daily challenges and leaderboards.
- **Rendering:** HDR pipeline (RenderPass → UnrealBloom → OutputPass/ACES), PCF soft shadows following the player, one-draw-call particles, and a shader sky.
- **Performance:** pixel ratio capped at 1.5, a "Performance" mode that turns off bloom and shadows (default on touch devices), shared geometries, and occluder culling for the camera.
- **Future backend:** Lovable Cloud (Postgres + Auth) for leaderboards, profiles and Echo sharing. Echo paths are small sample arrays (about 30 bytes per frame), cheap to store and stream.

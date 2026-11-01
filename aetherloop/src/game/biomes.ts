export interface Biome {
  name: string;
  skyTop: string; skyHorizon: string; skyBottom: string;
  fog: string; fogDensity: number;
  grass: string; rock: string; foliage: string; trunk: string;
  accent: string; accent2: string;
  sun: string; sunIntensity: number; hemi: number;
  cloud: string; hollow: string;
  rootHz: number;
}

export const BIOMES: Biome[] = [
  {
    name: 'Aurora Reach',
    skyTop: '#060d2e', skyHorizon: '#3b5fd0', skyBottom: '#070a20',
    fog: '#22306e', fogDensity: 0.0075,
    grass: '#4fc79e', rock: '#3a3d6a', foliage: '#76f0c6', trunk: '#4b3b5e',
    accent: '#59f3ff', accent2: '#b07cff',
    sun: '#d6e6ff', sunIntensity: 2.2, hemi: 0.9,
    cloud: '#8ea6ff', hollow: '#ff3d6e', rootHz: 110,
  },
  {
    name: 'Ember Atoll',
    skyTop: '#230818', skyHorizon: '#ff7a45', skyBottom: '#260b10',
    fog: '#7a3328', fogDensity: 0.0085,
    grass: '#d9a441', rock: '#5a2e2a', foliage: '#ff8a3c', trunk: '#3a1d17',
    accent: '#ffd166', accent2: '#ff5e5b',
    sun: '#ffd2a1', sunIntensity: 2.6, hemi: 0.8,
    cloud: '#ffb08a', hollow: '#9b4dff', rootHz: 98,
  },
  {
    name: 'Verdant Drift',
    skyTop: '#1b5fa8', skyHorizon: '#bfe9ff', skyBottom: '#2f6d8a',
    fog: '#9bd0ea', fogDensity: 0.006,
    grass: '#6cc552', rock: '#6b5844', foliage: '#2fa65a', trunk: '#5a3d2b',
    accent: '#fff27a', accent2: '#67ffb0',
    sun: '#fff5d6', sunIntensity: 3.0, hemi: 1.1,
    cloud: '#ffffff', hollow: '#ff2d55', rootHz: 130.81,
  },
  {
    name: 'Abyssal Bloom',
    skyTop: '#01040d', skyHorizon: '#0d4152', skyBottom: '#01030a',
    fog: '#06202a', fogDensity: 0.009,
    grass: '#1f6f78', rock: '#1a2433', foliage: '#ff5fd2', trunk: '#20283a',
    accent: '#3dffd6', accent2: '#ff5fd2',
    sun: '#7fd9ff', sunIntensity: 1.6, hemi: 0.8,
    cloud: '#2a5a6e', hollow: '#ffb300', rootHz: 82.41,
  },
  {
    name: 'Solar Choir',
    skyTop: '#2e1760', skyHorizon: '#ffc6e0', skyBottom: '#43255f',
    fog: '#c595d4', fogDensity: 0.0065,
    grass: '#efe2ff', rock: '#8a6fb3', foliage: '#ffc4ea', trunk: '#7a5a9a',
    accent: '#ff9ff3', accent2: '#ffe066',
    sun: '#fff0f8', sunIntensity: 2.8, hemi: 1.0,
    cloud: '#ffe6f4', hollow: '#00d5ff', rootHz: 146.83,
  },
];

export const biomeFor = (level: number) => BIOMES[(level - 1) % BIOMES.length];

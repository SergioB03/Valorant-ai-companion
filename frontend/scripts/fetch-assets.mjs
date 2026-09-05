// One-time asset pipeline: downloads the map splashes + agent icons the UI
// uses from media.valorant-api.com and emits resized WebP into src/assets/,
// where Vite fingerprints them (so the Caddyfile's immutable 1-year cache rule
// for /assets/* applies automatically).
//
// Why: the full-res CDN originals measure ~20 MB per fresh page session; the
// WebP set below is ~1.5 MB, and core UI semantics (the sentiment insignia)
// stop depending on a fan CDN's uptime. Re-run only if a map/agent is added:
//
//   npm run fetch-assets
//
// then commit the regenerated files. UUIDs must stay in sync with
// src/components/Backdrop.jsx and src/components/Insignia.jsx.

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MAPS_DIR = path.join(ROOT, "src", "assets", "maps");
const AGENTS_DIR = path.join(ROOT, "src", "assets", "agents");

// Same UUIDs as Backdrop.jsx (verified 2026-07 against valorant-api.com).
const MAPS = [
  { name: "ascent", uuid: "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319" },
  { name: "haven", uuid: "2bee0dc9-4ffe-519b-1cbd-7fbe763a6047" },
  { name: "bind", uuid: "2c9d57ec-4431-9c5e-2939-8f9ef6dd5cba" },
  { name: "icebox", uuid: "e2ad5c54-4114-a870-9641-8ea21279579a" },
  { name: "lotus", uuid: "2fe4ed3a-450a-948b-6d6b-e89a78e680a9" },
  { name: "split", uuid: "d960549e-485c-e861-8d71-aa9d1aed12a2" },
];

// Same UUIDs as Insignia.jsx (verified 2026-07 against valorant-api.com).
const AGENTS = [
  { name: "gekko", uuid: "e370fa57-4757-3604-3648-499e1f642d3f" },
  { name: "omen", uuid: "8e253930-4c05-31dd-1b6c-968525494517" },
  { name: "brimstone", uuid: "9f0d8ba9-4140-b941-57d3-a7ad57c6b417" },
  { name: "sage", uuid: "569fdd95-4d10-43ab-ca70-79becc718b46" },
  { name: "cypher", uuid: "117ed9e3-49f3-6512-3ccf-0cada7e3823b" },
];

const SPLASH_WIDTH = 1920; // full-viewport backdrop; q75 keeps ~150-250 KB each
const SPLASH_QUALITY = 75;
// 2x the rendered sizes: 18px insignia chip icon and 44px AgentBadge avatar.
const ICON_SIZES = [36, 88];

async function fetchBuffer(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return Buffer.from(await res.arrayBuffer());
}

function kb(buf) {
  return `${(buf.length / 1024).toFixed(0)} KB`;
}

async function run() {
  await mkdir(MAPS_DIR, { recursive: true });
  await mkdir(AGENTS_DIR, { recursive: true });
  let total = 0;

  for (const m of MAPS) {
    const url = `https://media.valorant-api.com/maps/${m.uuid}/splash.png`;
    const src = await fetchBuffer(url);
    const out = await sharp(src)
      .resize({ width: SPLASH_WIDTH, withoutEnlargement: true })
      .webp({ quality: SPLASH_QUALITY })
      .toBuffer();
    const file = path.join(MAPS_DIR, `${m.name}.webp`);
    await writeFile(file, out);
    total += out.length;
    console.log(`maps/${m.name}.webp  ${kb(src)} -> ${kb(out)}`);
  }

  for (const a of AGENTS) {
    const url = `https://media.valorant-api.com/agents/${a.uuid}/displayicon.png`;
    const src = await fetchBuffer(url);
    for (const size of ICON_SIZES) {
      const out = await sharp(src)
        .resize({ width: size, height: size, fit: "contain" })
        .webp({ quality: 80 })
        .toBuffer();
      const file = path.join(AGENTS_DIR, `${a.name}-${size}.webp`);
      await writeFile(file, out);
      total += out.length;
      console.log(`agents/${a.name}-${size}.webp  ${kb(src)} -> ${kb(out)}`);
    }
  }

  console.log(`\nTotal committed asset weight: ${(total / 1024 / 1024).toFixed(2)} MB`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});

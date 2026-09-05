// Generates public/og-card.png — the 1200x630 unfurl card referenced by the
// og:image / twitter:image tags in index.html. Pure app branding (no Riot
// assets, no fan-CDN art), rendered from inline SVG via sharp. Re-run with
//   node scripts/make-og-card.mjs
// and commit the output if the branding ever changes.

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "public", "og-card.png");

const W = 1200;
const H = 630;

const svg = `
<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#16222e"/>
      <stop offset="1" stop-color="#0f1923"/>
    </linearGradient>
    <linearGradient id="glow" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ff4655" stop-opacity="0"/>
      <stop offset="0.3" stop-color="#ff4655"/>
      <stop offset="0.7" stop-color="#ff4655"/>
      <stop offset="1" stop-color="#ff4655" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#bg)"/>
  <rect width="${W}" height="6" fill="url(#glow)"/>
  <!-- faint angled panel lines, echoing the app's cut-corner panels -->
  <path d="M0 ${H} L340 ${H} L420 ${H - 80} L0 ${H - 80} Z" fill="#ff4655" opacity="0.06"/>
  <path d="M${W} 0 L${W - 300} 0 L${W - 380} 90 L${W} 90 Z" fill="#7dd3fc" opacity="0.05"/>
  <!-- the app's V mark, scaled up -->
  <g transform="translate(140,150) scale(7.5)">
    <path fill="#ff4655" d="M4 7l11 14h6L8 7H4zm24 0h-6l-7 9 3 4L28 7z"/>
  </g>
  <text x="140" y="420" font-family="'Bebas Neue','Arial Narrow',Impact,sans-serif"
        font-size="92" font-style="italic" letter-spacing="10" fill="#ece8e1">VALORANT</text>
  <text x="140" y="500" font-family="'Bebas Neue','Arial Narrow',Impact,sans-serif"
        font-size="92" font-style="italic" letter-spacing="10" fill="#ff4655">AI COMPANION</text>
  <text x="142" y="560" font-family="Arial,Helvetica,sans-serif" font-size="26"
        fill="#9aa7b3">Match analysis &#183; tilt detection &#183; mental coaching &#183; meta Q&amp;A</text>
</svg>`;

await mkdir(path.dirname(OUT), { recursive: true });
const png = await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toBuffer();
await writeFile(OUT, png);
console.log(`og-card.png written (${(png.length / 1024).toFixed(0)} KB)`);

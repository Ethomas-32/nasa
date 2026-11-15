// Data access for the static export (docs/export_contract.md). Serve the REPO ROOT so that
// web/ and export/ are siblings: python -m http.server 8000 -> http://localhost:8000/web/
export const base = (region) => `../export/${region}/`;

const cache = new Map();
export async function getJSON(url) {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${url}`);
      return r.json();
    }));
  }
  return cache.get(url);
}

// Pixel-series tile name, matching export.write_pixel_series: f"{lat0:+06.1f}_{lon0:+07.1f}.json"
function signed(v, width) {
  const s = Math.abs(v).toFixed(1).padStart(width - 1, "0");
  return (v < 0 ? "-" : "+") + s;
}
export function tileName(lat, lon, size = 5) {
  const la = Math.floor(lat / size) * size, lo = Math.floor(lon / size) * size;
  return `${signed(la, 6)}_${signed(lo, 7)}.json`;
}

export async function cellAt(region, entry, lat, lon) {
  const ps = entry.pixel_series;
  if (!ps) return null;
  const name = tileName(lat, lon, ps.tile_deg);
  if (!ps.tiles.includes(name)) return null;
  const tile = await getJSON(`${base(region)}pixel_series/${ps.dir}/${name}`);
  let best = null, bestD = Infinity;
  for (const c of tile.cells) {
    const d = Math.hypot(c.lat - lat, (c.lon - lon) * Math.cos(lat * Math.PI / 180));
    if (d < bestD) { bestD = d; best = c; }
  }
  // only accept the cell actually under the click (half a grid step, with a little slack)
  const step = tile.cells.length > 1 ? Math.min(...tile.cells.map((c) => Math.abs(c.lat - tile.cells[0].lat)).filter((x) => x > 0)) : 1;
  if (!best || bestD > step * 0.9) return null;
  return { ...best, years: tile.years, units: tile.units };
}

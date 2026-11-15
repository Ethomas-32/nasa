// The exported PNGs are regular latitude/longitude grids, but MapLibre draws in Web Mercator and
// interpolates an image source linearly in projected space. Placing the PNG directly would shift
// rows by up to ~1 degree over CONUS. So each output row is re-sampled from the source row at the
// right latitude before the image is handed to the map.
const D2R = Math.PI / 180;
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * D2R) / 2));
const invMercY = (y) => (2 * Math.atan(Math.exp(y)) - Math.PI / 2) / D2R;

function loadImage(url) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = () => rej(new Error(`image ${url}`));
    img.src = url;
  });
}

export async function mercatorImage(url, bounds, scale = 4) {
  const img = await loadImage(url);
  const { north, south } = bounds;
  const H = img.height, W = img.width;
  const outH = H * scale, outW = W * scale;
  const c = document.createElement("canvas");
  c.width = outW; c.height = outH;
  const ctx = c.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const yN = mercY(north), yS = mercY(south);
  for (let k = 0; k < outH; k++) {
    const lat = invMercY(yN - ((k + 0.5) / outH) * (yN - yS));
    const row = Math.min(H - 1, Math.max(0, Math.floor(((north - lat) / (north - south)) * H)));
    ctx.drawImage(img, 0, row, W, 1, 0, k, outW, 1);
  }
  return c.toDataURL("image/png");
}

export function corners(b) {
  return [[b.west, b.north], [b.east, b.north], [b.east, b.south], [b.west, b.south]];
}

export function rampCSS(colors) {
  return `linear-gradient(to right, ${colors.join(", ")})`;
}

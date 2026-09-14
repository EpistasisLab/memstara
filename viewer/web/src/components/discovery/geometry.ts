export interface Point3 { x: number; y: number; z: number }
export interface Camera { yaw: number; pitch: number; zoom: number }
export function pointForId(id: number): Point3 {
  const hash = (n: number) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const y = hash(id) * 1.8 - .9, a = hash(id + 999) * Math.PI * 2;
  const r = Math.sqrt(1 - y * y);
  return { x: r * Math.cos(a), y, z: r * Math.sin(a) };
}
export function cameraForPoint(p: Point3): Camera {
  return { yaw: -Math.atan2(p.x, p.z), pitch: Math.atan2(p.y, Math.hypot(p.x, p.z)), zoom: 1.22 };
}
export function angleDelta(a: number, b: number) { return Math.atan2(Math.sin(b - a), Math.cos(b - a)); }
export function project(p: Point3, camera: Camera, w: number, h: number) {
  const x = p.x * Math.cos(camera.yaw) + p.z * Math.sin(camera.yaw);
  const z0 = p.z * Math.cos(camera.yaw) - p.x * Math.sin(camera.yaw);
  const y = p.y * Math.cos(camera.pitch) - z0 * Math.sin(camera.pitch);
  const z = p.y * Math.sin(camera.pitch) + z0 * Math.cos(camera.pitch);
  const perspective = 3 / (3 - z), radius = Math.min(w * .34, h * .37) * camera.zoom;
  return { x: w / 2 + x * radius * perspective, y: h * .49 + y * radius * perspective, z, perspective };
}
export interface LabelRect { x: number; y: number; w: number; h: number }
export function overlaps(a: LabelRect, b: LabelRect, gap = 12) {
  return a.x < b.x + b.w + gap && a.x + a.w + gap > b.x && a.y < b.y + b.h + gap && a.y + a.h + gap > b.y;
}

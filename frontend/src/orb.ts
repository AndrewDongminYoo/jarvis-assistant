// orb.ts — Three.js audio-reactive particle orb
import * as THREE from "three";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

const STATE_COLORS: Record<OrbState, THREE.Color> = {
  idle: new THREE.Color(0x1144aa),
  listening: new THREE.Color(0x44aaff),
  thinking: new THREE.Color(0xffaa44),
  speaking: new THREE.Color(0x44ffaa),
};

const N = 3000;
const R = 1.2;

let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer: THREE.WebGLRenderer;
let pts: THREE.Points;
let base: Float32Array;
let live: Float32Array;
let cols: Float32Array;
let state: OrbState = "idle";
let level = 0;
let clock: THREE.Clock;

export function init(canvas: HTMLCanvasElement): void {
  clock = new THREE.Clock();
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(
    60,
    canvas.width / canvas.height,
    0.1,
    100,
  );
  camera.position.z = 4;

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0);

  const geo = new THREE.BufferGeometry();
  base = new Float32Array(N * 3);
  live = new Float32Array(N * 3);
  cols = new Float32Array(N * 3);

  // Fibonacci lattice — even distribution on sphere surface
  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = (1 - (i / (N - 1)) * 2) * R;
    const r = Math.sqrt(Math.max(R * R - y * y, 0));
    const t = phi * i;
    base[i * 3] = live[i * 3] = Math.cos(t) * r;
    base[i * 3 + 1] = live[i * 3 + 1] = y;
    base[i * 3 + 2] = live[i * 3 + 2] = Math.sin(t) * r;
  }

  geo.setAttribute("position", new THREE.BufferAttribute(live, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(cols, 3));

  pts = new THREE.Points(
    geo,
    new THREE.PointsMaterial({
      size: 0.012,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      sizeAttenuation: true,
    }),
  );
  scene.add(pts);

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  requestAnimationFrame(tick);
}

function tick(): void {
  requestAnimationFrame(tick);
  const t = clock.getElapsedTime();
  const col = STATE_COLORS[state];
  const pulse = state === "idle" ? 0.04 * Math.sin(t * 1.2) : level * 0.5;

  for (let i = 0; i < N; i++) {
    const ox = base[i * 3];
    const oy = base[i * 3 + 1];
    const oz = base[i * 3 + 2];
    const noise =
      Math.sin(ox * 3 + t) * Math.cos(oy * 3 + t * 0.7) * 0.08 +
      pulse * Math.sin(i * 0.01 + t * 2);
    const s = 1 + noise;
    live[i * 3] = ox * s;
    live[i * 3 + 1] = oy * s;
    live[i * 3 + 2] = oz * s;
    const b = 0.7 + 0.3 * Math.abs(noise) + level * 0.3;
    cols[i * 3] = col.r * b;
    cols[i * 3 + 1] = col.g * b;
    cols[i * 3 + 2] = col.b * b;
  }

  (pts.geometry.attributes["position"] as THREE.BufferAttribute).needsUpdate =
    true;
  (pts.geometry.attributes["color"] as THREE.BufferAttribute).needsUpdate =
    true;
  pts.rotation.y = t * 0.1;
  pts.rotation.x = t * 0.04;
  renderer.render(scene, camera);
}

export function setState(s: OrbState): void {
  state = s;
}

export function setAudioLevel(v: number): void {
  level = v;
}

/**
 * vr-text-panel.js
 * Emotion-colour panel for in-VR display below the sphere.
 * Default: transparent white glow. Colour shifts based on EEG emotion.
 */

import * as THREE from 'three';

// ─── Configuration ───────────────────────────────────────────────────────
const CANVAS_W = 512;
const CANVAS_H = 512;
const PANEL_WORLD_W = 0.6;   // metres — square panel
const PANEL_WORLD_H = 0.6;

// Default: transparent white
const DEFAULT_COLOR = { r: 255, g: 255, b: 255, a: 0.15 };

/**
 * Create a colour-panel mesh for VR display.
 * @returns {THREE.Mesh} — mesh with .userData.setColor(r,g,b,a) method
 */
export function createTextPanel(options = {}) {
  const worldW = options.width ?? PANEL_WORLD_W;
  const worldH = options.height ?? PANEL_WORLD_H;

  const canvas = document.createElement('canvas');
  canvas.width = CANVAS_W;
  canvas.height = CANVAS_H;
  const ctx = canvas.getContext('2d');

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;

  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });

  const geometry = new THREE.CircleGeometry(worldW * 0.5, 48);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'vr-emotion-panel';
  mesh.renderOrder = 9999;
  mesh.frustumCulled = false;

  mesh.userData._canvas = canvas;
  mesh.userData._ctx = ctx;
  mesh.userData._texture = texture;
  mesh.userData._lastKey = '';

  // Current & target colour (for smooth lerp)
  mesh.userData._current = { ...DEFAULT_COLOR };
  mesh.userData._target = { ...DEFAULT_COLOR };

  /**
   * Set target colour. The panel will lerp towards it each frame.
   * @param {number} r 0-255
   * @param {number} g 0-255
   * @param {number} b 0-255
   * @param {number} a 0-1
   */
  mesh.userData.setColor = (r, g, b, a) => {
    mesh.userData._target = { r, g, b, a };
  };

  /**
   * Legacy text update — maps to setColor via a simple keyword check.
   * Keeps compatibility with existing app.js calls.
   */
  mesh.userData.update = (text) => {
    // Just ignore text updates now — colour is driven by setColor
  };

  /**
   * Call once per frame to smoothly animate colour.
   * @param {number} dt — delta time in seconds (optional, default 0.016)
   */
  mesh.userData.tick = (dt) => {
    const speed = 3.0; // colour blend speed
    const t = Math.min(1, (dt || 0.016) * speed);
    const c = mesh.userData._current;
    const tgt = mesh.userData._target;

    c.r += (tgt.r - c.r) * t;
    c.g += (tgt.g - c.g) * t;
    c.b += (tgt.b - c.b) * t;
    c.a += (tgt.a - c.a) * t;

    _drawGlow(ctx, canvas, c.r, c.g, c.b, c.a);
    texture.needsUpdate = true;
  };

  // Draw initial default state
  _drawGlow(ctx, canvas, DEFAULT_COLOR.r, DEFAULT_COLOR.g, DEFAULT_COLOR.b, DEFAULT_COLOR.a);
  texture.needsUpdate = true;

  return mesh;
}

/**
 * Draw a soft radial glow on the canvas.
 */
function _drawGlow(ctx, canvas, r, g, b, a) {
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const radius = w * 0.48;

  ctx.clearRect(0, 0, w, h);

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
  const ri = Math.round(r);
  const gi = Math.round(g);
  const bi = Math.round(b);
  grad.addColorStop(0,   `rgba(${ri},${gi},${bi},${(a * 0.9).toFixed(3)})`);
  grad.addColorStop(0.4, `rgba(${ri},${gi},${bi},${(a * 0.5).toFixed(3)})`);
  grad.addColorStop(1,   `rgba(${ri},${gi},${bi},0)`);

  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
}

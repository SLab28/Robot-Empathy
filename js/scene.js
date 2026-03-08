// scene.js — Three.js scene, camera, renderer
// HIDDEN Exhibition · AR Point Cloud Experience

import * as THREE from 'three';
import { uniforms } from '../uniformsRegistry.js';

/**
 * Create and return the core Three.js objects.
 * Renderer is XR-ready; camera is managed by WebXR during Phase 2.
 * @returns {{ scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer }}
 */
export function createScene() {
  const scene = new THREE.Scene();

  // Camera — WebXR overrides projection + view matrices in AR mode
  // Fallback position for non-AR / AR.js Phase 1
  const camera = new THREE.PerspectiveCamera(
    120, // Adjusted FOV from 71 to 120 degrees
    window.innerWidth / window.innerHeight,
    0.01,
    100
  );
  camera.position.set(0, 1.0, 3);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 1.0);
  document.body.appendChild(renderer.domElement);

  // Resize handler (only applies outside XR session)
  window.addEventListener('resize', () => {
    if (!renderer.xr.isPresenting) {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }
  });

  return { scene, camera, renderer };
}

/**
 * Animation loop - updates uniforms before render
 * Call this each frame before renderer.render()
 */
export function updateUniforms() {
  uniforms.time.value = performance.now() * 0.001;
}

/**
 * Dispose of all scene resources.
 * @param {THREE.WebGLRenderer} renderer
 * @param {THREE.Scene} scene
 */
export function disposeScene(renderer, scene) {
  scene.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) {
        obj.material.forEach((m) => m.dispose());
      } else {
        obj.material.dispose();
      }
    }
  });
  renderer.dispose();
}

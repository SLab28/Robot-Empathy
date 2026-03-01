// webxr-session.js — WebXR immersive-ar session with hit-test + reticle
// HIDDEN Exhibition · AR Point Cloud Experience

import * as THREE from 'three';
import { uniforms } from '../uniformsRegistry.js';

let xrSession = null;
let hitTestSource = null;
let referenceSpace = null;
let _onFrame = null;
let _reticle = null;
let _currentHitPose = null;
let wakeLockSentinel = null; // Store wake lock for cleanup
let xrLightProbe = null;

function updateXRLightUniforms(frame) {
  if (!xrLightProbe || !frame) return;

  const estimate = frame.getLightEstimate(xrLightProbe);
  if (!estimate || !estimate.primaryLightIntensity) return;

  const r = Math.max(estimate.primaryLightIntensity.x, 0.0001);
  const g = Math.max(estimate.primaryLightIntensity.y, 0.0001);
  const b = Math.max(estimate.primaryLightIntensity.z, 0.0001);
  const avg = (r + g + b) / 3.0;

  // Tone-map raw intensity to a stable range for point cloud shading.
  const mappedIntensity = THREE.MathUtils.clamp(Math.log2(1.0 + avg) * 0.35, 0.45, 1.75);
  uniforms.xrLightIntensity.value = mappedIntensity;

  const maxChannel = Math.max(r, g, b);
  uniforms.xrLightColor.value.set(r / maxChannel, g / maxChannel, b / maxChannel);
}

/**
 * Check if immersive-ar is supported on this device.
 * @returns {Promise<boolean>}
 */
export async function isWebXRSupported() {
  console.log('[WebXR] Checking support...');
  console.log('[WebXR] navigator.xr exists:', !!navigator.xr);
  
  if (!navigator.xr) {
    console.log('[WebXR] No navigator.xr found');
    return false;
  }
  
  try {
    const supported = await navigator.xr.isSessionSupported('immersive-vr');
    console.log('[WebXR] immersive-vr supported:', supported);
    
    // For emulators, also check if requestSession is available
    const canRequest = typeof navigator.xr.requestSession === 'function';
    console.log('[WebXR] requestSession available:', canRequest);
    
    // Return true if either is supported (some emulators might not report correctly)
    return supported || canRequest;
  } catch (err) {
    console.warn('[WebXR] Support check failed:', err);
    // Still return true if requestSession exists (for emulator compatibility)
    return typeof navigator.xr.requestSession === 'function';
  }
}

/**
 * Create the reticle mesh — white wireframe square, flat on floor.
 * @param {number} size — side length in metres
 * @returns {THREE.LineSegments}
 */
function createReticle(size = 0.35) {
  // Create a square wireframe reticle
  const geometry = new THREE.PlaneGeometry(size, size);
  const edges = new THREE.EdgesGeometry(geometry);
  const material = new THREE.LineBasicMaterial({ 
    color: 0xffffff, 
    linewidth: 3
  });
  const reticle = new THREE.LineSegments(edges, material);
  reticle.name = 'placement-reticle';
  reticle.rotateX(-Math.PI / 2); // flat on floor
  reticle.frustumCulled = false;
  reticle.visible = false;
  console.log('[WebXR] Created square wireframe reticle, size:', size);
  geometry.dispose(); // edges cloned it
  return reticle;
}

/**
 * Start a WebXR immersive-vr session with auto-placement.
 *
 * @param {THREE.WebGLRenderer} renderer
 * @param {THREE.Scene} scene
 * @param {THREE.PerspectiveCamera} camera
 * @param {object} callbacks
 * @param {function} callbacks.onPlace — called once when user taps to place (hitPose)
 * @param {function} [callbacks.onSessionEnd] — called when session ends
 * @returns {Promise<{ session: XRSession, referenceSpace: XRReferenceSpace }>}
 */
export async function startWebXRSession(renderer, scene, camera, callbacks = {}) {
  const arOverlay = document.getElementById('ar-overlay');
  const arStatus = document.getElementById('ar-status');

  // Build feature lists with reference space negotiation
  const requiredFeatures = [];
  const optionalFeatures = ['dom-overlay', 'unbounded', 'local-floor', 'local', 'viewer'];
  const sessionInit = {
    requiredFeatures,
    optionalFeatures,
  };

  // Attach DOM overlay if element exists
  if (arOverlay) {
    sessionInit.domOverlay = { root: arOverlay };
  }

  // Request session
  console.log('[WebXR] Requesting immersive-vr session…');
  console.log('[WebXR] Session init:', sessionInit);
  
  try {
    xrSession = await navigator.xr.requestSession('immersive-vr', sessionInit);
    console.log('[WebXR] Session started successfully');
    console.log('[WebXR] Session environment integration:', xrSession.environmentIntegration);
  } catch (err) {
    console.error('[WebXR] Session request failed:', err);
    console.log('[WebXR] Error name:', err.name);
    console.log('[WebXR] Error message:', err.message);
    throw err;
  }

  // Show DOM overlay
  if (arOverlay) arOverlay.classList.remove('hidden');
  if (arStatus) arStatus.textContent = 'Positioning sphere…';

  // Prevent anything from hiding the DOM overlay root during WebXR
  let overlayObserver = null;
  if (arOverlay) {
    overlayObserver = new MutationObserver(() => {
      if (arOverlay.style.display === 'none' || arOverlay.classList.contains('hidden')) {
        arOverlay.classList.remove('hidden');
        arOverlay.style.display = '';
        console.warn('[WebXR] Prevented DOM overlay root from being hidden');
      }
    });
    overlayObserver.observe(arOverlay, { attributes: true, attributeFilter: ['class', 'style'] });
  }

  // Enable XR on renderer now (not earlier — interferes with Phase 1 canvas)
  renderer.xr.enabled = true;

  // Bind session to Three.js renderer
  await renderer.xr.setSession(xrSession);

  // Reference spaces - use viewer space for emulator compatibility
  let viewerSpace;
  try {
    viewerSpace = await xrSession.requestReferenceSpace('viewer');
    console.log('[WebXR] Viewer reference space created');
  } catch (err) {
    console.error('[WebXR] Failed to create viewer space:', err);
    throw err;
  }

  // Prefer unbounded space for vast/infinite-feel VR environments.
  async function getReferenceSpace(session) {
    const types = ['unbounded', 'local-floor', 'local', 'viewer'];
    for (const type of types) {
      try {
        const refSpace = await session.requestReferenceSpace(type);
        console.log('[WebXR] Using reference space:', type);
        return refSpace;
      } catch (e) {
        console.warn('[WebXR] Reference space not supported:', type, e.name);
      }
    }
    throw new Error('No supported reference space found');
  }

  try {
    referenceSpace = await getReferenceSpace(xrSession);
  } catch (err) {
    console.error('[WebXR] Failed to get any reference space:', err);
    throw err;
  }

  // VR mode: use neutral light defaults (no AR light-estimation probe).
  xrLightProbe = null;
  uniforms.xrLightIntensity.value = 1.0;
  uniforms.xrLightColor.value.set(1, 1, 1);

  // Auto-placement state
  _currentHitPose = null;
  let placed = false;

  // Session end handler
  xrSession.addEventListener('end', () => {
    console.log('[WebXR] Session ended');
    xrSession = null;
    hitTestSource = null;
    referenceSpace = null;
    xrLightProbe = null;
    _currentHitPose = null;
    uniforms.xrLightIntensity.value = 1.0;
    uniforms.xrLightColor.value.set(1, 1, 1);
    
    // Release wake lock when session ends
    releaseWakeLock();
    
    // Disconnect overlay observer
    if (overlayObserver) {
      overlayObserver.disconnect();
    }
    
    // Restore DOM overlay root visibility for potential re-entry
    if (arOverlay) {
      arOverlay.style.opacity = '';
      arOverlay.style.pointerEvents = '';
      arOverlay.style.transition = '';
    }
    
    if (callbacks.onSessionEnd) callbacks.onSessionEnd();
  });

  // XR render loop via Three.js
  _onFrame = (timestamp, frame) => {
    if (!frame) {
      renderer.render(scene, camera);
      return;
    }

    // Auto-place once: 1.5m in front of viewer, 1.6m high.
    if (!placed) {
      const viewerPose = frame.getViewerPose(referenceSpace);
      if (viewerPose && viewerPose.views && viewerPose.views.length > 0) {
        const t = viewerPose.transform;
        const q = new THREE.Quaternion(
          t.orientation.x,
          t.orientation.y,
          t.orientation.z,
          t.orientation.w
        );
        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(q).normalize();

        _currentHitPose = {
          position: {
            x: t.position.x + forward.x * 1.5,
            y: 1.6,
            z: t.position.z + forward.z * 1.5,
          },
          orientation: t.orientation,
          matrix: t.matrix,
        };

        placed = true;
        console.log('[WebXR] Auto-placed object in front of viewer');
        if (callbacks.onPlace) callbacks.onPlace(_currentHitPose);
      }
    }

    // Update animation uniforms from app loop
    if (window.updateAnimations) {
      window.updateAnimations();
    }

    // Update shader light response from WebXR light estimation (AR-only path)
    if (xrLightProbe) updateXRLightUniforms(frame);
    
    renderer.render(scene, camera);
  };

  renderer.setAnimationLoop(_onFrame);

  return { session: xrSession, referenceSpace };
}

/**
 * Stop the hit-test source (call after tree is placed).
 */
export function stopHitTest() {
  if (hitTestSource) {
    hitTestSource.cancel();
    hitTestSource = null;
    console.log('[WebXR] Hit-test stopped');
  }
}

/**
 * End the WebXR session.
 */
export async function endWebXRSession() {
  if (xrSession) {
    await xrSession.end();
  }
}

/**
 * Request screen wake lock to prevent dimming.
 * @returns {Promise<WakeLockSentinel|null>}
 */
export async function requestWakeLock() {
  if (!('wakeLock' in navigator)) {
    console.warn('[WebXR] Wake Lock API not supported');
    return null;
  }
  try {
    // Release any existing wake lock
    if (wakeLockSentinel) {
      await wakeLockSentinel.release();
      wakeLockSentinel = null;
    }
    
    const sentinel = await navigator.wakeLock.request('screen');
    wakeLockSentinel = sentinel;
    console.log('[WebXR] Wake lock acquired');
    sentinel.addEventListener('release', () => {
      console.log('[WebXR] Wake lock released');
      wakeLockSentinel = null;
    });
    return sentinel;
  } catch (err) {
    console.warn('[WebXR] Wake lock failed:', err);
    return null;
  }
}

/**
 * Release the wake lock if active.
 */
export async function releaseWakeLock() {
  if (wakeLockSentinel) {
    try {
      await wakeLockSentinel.release();
      console.log('[WebXR] Wake lock manually released');
      wakeLockSentinel = null;
    } catch (err) {
      console.warn('[WebXR] Failed to release wake lock:', err);
    }
  }
}

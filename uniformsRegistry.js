import * as THREE from 'three';

export const uniforms = {
  // Core — updated every frame
  time:            { value: 0 },
  pointSize:       { value: 0.03 },

  // Noise displacement (tree body)
  noiseScale:      { value: 2.0 },
  noiseAmp:        { value: 0.03 },

  // Glow (fragment shader)
  glowIntensity:   { value: 1.0 },
  glowRadius:      { value: 0.55 },

  // Firefly drift / flocking (vertex shader)
  flockSpeed:      { value: 0.001 },
  flockSpread:     { value: 8.0 },
  driftSpeed:      { value: 0.03 },
  driftHeight:     { value: 2.5 },

  // Audio reactivity (Phase 6+)
  audioAmp:        { value: 0.0 },
  sphereAudioLevel:{ value: 0.0 },
  sphereAudioTimbre:{ value: 0.0 },

  // WebXR light estimation (updated per XR frame when available)
  xrLightColor:    { value: new THREE.Color(1.0, 1.0, 1.0) },
  xrLightIntensity:{ value: 1.0 },

  // Opacity for fade-in animation
  uOpacity:        { value: 1.0 },

  // TODO: test AdditiveBlending vs NormalBlending once shaders are visually verified
  // Change blending mode in point-cloud-loader.js ShaderMaterial creation
};

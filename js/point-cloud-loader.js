// point-cloud-loader.js — Bubble sphere shader loader (temporary swap)
// HIDDEN Exhibition · AR Point Cloud Experience

import * as THREE from 'three';
import { uniforms } from '../uniformsRegistry.js';

const shellNoise = `
float _h3(vec3 p){
  p = fract(p * vec3(443.537, 537.247, 247.428));
  p += dot(p, p.yzx + 19.19);
  return fract((p.x + p.y) * p.z);
}
float _n3(vec3 p){
  vec3 i = floor(p), f = fract(p);
  f = f*f*(3.0-2.0*f);
  return mix(
    mix(mix(_h3(i),              _h3(i+vec3(1,0,0)), f.x),
        mix(_h3(i+vec3(0,1,0)),  _h3(i+vec3(1,1,0)), f.x), f.y),
    mix(mix(_h3(i+vec3(0,0,1)), _h3(i+vec3(1,0,1)), f.x),
        mix(_h3(i+vec3(0,1,1)), _h3(i+vec3(1,1,1)), f.x), f.y), f.z);
}
float _fbm3(vec3 p){
  float v=0.0, a=0.5;
  for(int i=0;i<3;i++){ v += a*_n3(p); p = p*2.02 + vec3(1.1,3.7,2.3); a *= 0.5; }
  return v;
}
`;

const frameVertSrc = `
precision highp float;
uniform float time;
uniform float bubbleRadius;
uniform float shellThick;
uniform float sphereAudioLevel;
uniform float sphereAudioTimbre;
uniform float shellRole;

varying vec3  vLocalPos;
varying vec3  vOrigPos;
varying vec3  vWorldNormal;
varying vec3  vWorldPos;
varying float vDisplace;

${shellNoise}

void main() {
  vOrigPos = position;
  vec3 n = normalize(position);
  float slow = time * 0.28;
  float fast = time * 0.55;

  // Voice reactivity: loudness scales sine frequency (outer shell only).
  float aLevel = clamp(sphereAudioLevel, 0.0, 1.0);
  float freqScale = 1.0 + (aLevel * 2.0 * shellRole);
  float slowFreq = slow * freqScale;
  float fastFreq = fast * freqScale;

  float sineWave = 0.0;
  sineWave += sin(n.x * (3.1 * freqScale) + slowFreq) * 0.55;
  sineWave += sin(n.y * (2.7 * freqScale) - slowFreq * 0.8) * 0.40;
  sineWave += sin(n.z * (3.5 * freqScale) + fastFreq * 0.4) * 0.30;
  sineWave += sin(dot(n, vec3(1.7, 2.3, 1.1)) * (4.2 * freqScale) + slowFreq * 1.1) * 0.25;
  sineWave += sin(dot(n, vec3(-1.3, 1.8, 2.1)) * (3.8 * freqScale) - fastFreq * 0.6) * 0.20;
  float noiseDisp = _fbm3(n * 4.5 + vec3(slow * 0.4, fast * 0.25, slow * 0.3));
  float noiseWave = (noiseDisp * 2.0 - 1.0) * 0.18;

  float wave = sineWave + noiseWave;

  float amp = shellThick * 0.55;
  float disp = wave * amp;

  vDisplace = disp;
  vLocalPos = position + n * disp;
  vWorldNormal = normalize(mat3(modelMatrix) * n);
  vWorldPos = (modelMatrix * vec4(vLocalPos, 1.0)).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(vLocalPos, 1.0);
}
`;

const outerFragSrc = `
precision highp float;
uniform float frameBrightness;
uniform float bubbleRadius;
uniform float openAngle;
varying vec3  vLocalPos;

void main() {
  float cutZ = bubbleRadius * cos(radians(openAngle));
  if (vLocalPos.z > cutZ) discard;
  gl_FragColor = vec4(vec3(frameBrightness), 1.0);
}
`;

const innerFragSrc = `
precision highp float;
#define PI  3.14159265359
#define TAU 6.28318530718

uniform float emissiveStrength;
uniform float bubbleRadius;
uniform float openAngle;
uniform float time;

varying vec3  vLocalPos;
varying vec3  vOrigPos;
varying vec3  vWorldNormal;
varying vec3  vWorldPos;
varying float vDisplace;

float _h3(vec3 p){
  p=fract(p*vec3(443.537,537.247,247.428));
  p+=dot(p,p.yzx+19.19);
  return fract((p.x+p.y)*p.z);
}
float _n3(vec3 p){
  vec3 i=floor(p),f=fract(p);
  f=f*f*(3.0-2.0*f);
  return mix(
    mix(mix(_h3(i),_h3(i+vec3(1,0,0)),f.x),mix(_h3(i+vec3(0,1,0)),_h3(i+vec3(1,1,0)),f.x),f.y),
    mix(mix(_h3(i+vec3(0,0,1)),_h3(i+vec3(1,0,1)),f.x),mix(_h3(i+vec3(0,1,1)),_h3(i+vec3(1,1,1)),f.x),f.y),f.z);
}
float _fbm3(vec3 p){
  float v=0.0,a=0.5;
  for(int i=0;i<3;i++){v+=a*_n3(p);p=p*2.02+vec3(1.1,3.7,2.3);a*=0.5;}
  return v;
}
vec3 nacrePalette(float t) {
  vec3 a = vec3(0.92, 0.88, 0.84);
  vec3 b = vec3(0.08, 0.06, 0.10);
  vec3 c = vec3(1.0,  1.0,  1.0);
  vec3 d = vec3(0.00, 0.35, 0.60);
  return clamp(a + b * cos(TAU * (c * t + d)), 0.0, 1.0);
}
vec3 orientPalette(float t) {
  vec3 a = vec3(0.80, 0.78, 0.82);
  vec3 b = vec3(0.18, 0.14, 0.16);
  vec3 c = vec3(1.0,  1.0,  1.0);
  vec3 d = vec3(0.55, 0.20, 0.80);
  return clamp(a + b * cos(TAU * (c * t + d)), 0.0, 1.0);
}

void main() {
  float cutZ = bubbleRadius * cos(radians(openAngle));
  if (vLocalPos.z > cutZ) discard;

  vec3 N = normalize(-vWorldNormal);
  vec3 viewDir = normalize(cameraPosition - vWorldPos);
  float cosV = max(dot(N, viewDir), 0.0);

  vec3 nOrig = normalize(vOrigPos);
  float slow = time * 0.09;
  float drift  = _fbm3(nOrig * 3.2 + vec3(slow, slow * 0.7, slow * 0.5));
  float drift2 = _fbm3(nOrig * 5.1 - vec3(slow * 0.6, slow * 0.8, slow * 0.4) + vec3(4.2));

  float nacrePh = drift * 0.6 + cosV * 0.35 + vDisplace * 4.0 + time * 0.04;
  vec3 nacreCol = nacrePalette(nacrePh);
  float orientPh = drift2 * 0.8 + cosV * 1.8 + time * 0.06;
  vec3 orientCol = orientPalette(orientPh);
  float frOrient = pow(1.0 - cosV, 2.2) * (0.5 + 0.5 * drift2);
  vec3 col = mix(nacreCol, orientCol, frOrient * 0.65);

  vec3 ssCol = vec3(0.98, 0.93, 0.85);
  float ssCos = pow(cosV, 0.6);
  col = mix(col, ssCol, ssCos * 0.22);

  vec3 lightDir1 = normalize(vec3(-0.4, 0.9, 0.5));
  float spec1 = pow(max(dot(reflect(-lightDir1, N), viewDir), 0.0), 55.0);
  vec3 lightDir2 = normalize(vec3(0.6, 0.7, -0.3));
  float spec2 = pow(max(dot(reflect(-lightDir2, N), viewDir), 0.0), 8.0) * 0.18;
  col += vec3(0.95, 0.97, 1.00) * spec1 * 0.70;
  col += vec3(1.00, 0.95, 0.88) * spec2;

  float cutR = sqrt(max(0.0, bubbleRadius*bubbleRadius - cutZ*cutZ));
  float dRim = length(vec2(length(vLocalPos.xy) - cutR, vLocalPos.z - cutZ));
  float rimGlow = emissiveStrength * (1.0 - smoothstep(0.0, bubbleRadius * 0.50, dRim));
  float radN = length(vLocalPos.xy) / max(cutR, 0.001);
  float lbx = emissiveStrength * 0.14 * (1.0 - smoothstep(0.05, 1.0, radN));

  col += nacreCol * rimGlow * 0.12;
  col += vec3(rimGlow * 0.14);
  col += vec3(lbx);

  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`;

const oceanVertSrc = `
precision highp float;
uniform float time;
uniform float bubbleRadius;
uniform mat4  uReflectMatrix;
varying vec2  vUv;
varying vec3  vWorldPos;
varying float vWave;
varying vec4  vReflCoord;

float h2(vec2 p){ p=fract(p*vec2(234.34,435.345)); p+=dot(p,p+34.23); return fract(p.x*p.y); }
float n2(vec2 p){ vec2 i=floor(p),f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(h2(i),h2(i+vec2(1,0)),u.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),u.x),u.y); }
float fbm2(vec2 p){ float v=0.0,a=0.5; for(int i=0;i<4;i++){v+=a*n2(p);p=p*2.1+vec2(1.3,0.7);a*=0.5;} return v; }

void main() {
  vUv = uv;
  vec3 pos = position;
  float t = time * 0.18;
  vec2 warpedUv = pos.xz * 0.35;
  vec2 q = vec2(fbm2(warpedUv + t * vec2(0.4, 0.3)), fbm2(warpedUv + t * vec2(-0.35, 0.45) + vec2(5.2, 1.3)));
  float wave = fbm2(warpedUv + 4.0 * q) * 0.08 - 0.04;
  pos.y += wave;
  vWave = wave;
  vec4 worldPos = modelMatrix * vec4(pos, 1.0);
  vWorldPos = worldPos.xyz;
  vReflCoord = uReflectMatrix * worldPos;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`;

const oceanFragSrc = `
precision highp float;
#define PI  3.14159265359
#define TAU 6.28318530718

uniform float time;
uniform float bubbleRadius;
uniform sampler2D uReflection;
varying vec2  vUv;
varying vec3  vWorldPos;
varying float vWave;
varying vec4  vReflCoord;

float h2(vec2 p){ p=fract(p*vec2(234.34,435.345)); p+=dot(p,p+34.23); return fract(p.x*p.y); }
float n2(vec2 p){ vec2 i=floor(p),f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(h2(i),h2(i+vec2(1,0)),u.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),u.x),u.y); }
float fbm(vec2 p, int oct){
  float v=0.0,a=0.5;
  for(int i=0;i<6;i++){
    if(i>=oct) break;
    v+=a*n2(p);p=p*2.1+vec2(1.3,0.7);a*=0.5;
  }
  return v;
}

void main(){
  // Discard fragments inside the sphere's vertical column
  float distFromAxis = length(vWorldPos.xz);
  if (distFromAxis < bubbleRadius * 0.98) discard;

  float tt  = time * 0.18;
  vec2  uv  = vWorldPos.xz * 0.28;

  // Planar reflection UV
  vec2 reflUV = vReflCoord.xy / vReflCoord.w;

  // Gentle ripple distortion
  float px = n2(uv * 2.4 + vec2(tt * 0.28, 0.0)) * 2.0 - 1.0;
  float py = n2(uv * 2.4 + vec2(0.0, tt * 0.22) + vec2(5.1)) * 2.0 - 1.0;
  reflUV  += vec2(px, py) * 0.014 + vec2(vWave * 6.0) * 0.012;
  reflUV   = clamp(reflUV, 0.001, 0.999);

  vec3 reflColor = texture2D(uReflection, reflUV).rgb;

  // Fresnel (Schlick)
  vec3  viewDir  = normalize(cameraPosition - vWorldPos);
  float cosTheta = max(dot(viewDir, vec3(0.0, 1.0, 0.0)), 0.0);
  float r0      = 0.15;
  float fresnel = r0 + (1.0 - r0) * pow(1.0 - cosTheta, 5.0);

  // Surface colour: pure reflection, faint cool-white tint
  vec3 waterTint = vec3(0.94, 0.97, 1.00);
  vec3 col = mix(waterTint, reflColor, 0.97);

  // Tiny specular glint on wave crests
  float glint = pow(max(0.0, vWave * 14.0 + 0.2), 4.0);
  col += vec3(1.0) * glint * 0.15;

  // Edge fade
  float dist     = length(vWorldPos.xz);
  float edgeFade = 1.0 - smoothstep(14.0, 20.0, dist);

  // Alpha driven by Fresnel: transparent center, mirror at edges
  float alpha = clamp(fresnel + 0.12, 0.0, 0.96) * edgeFade;

  // Smooth the hole edge left by the discard above
  float holeEdge = smoothstep(bubbleRadius * 0.98, bubbleRadius * 1.10, distFromAxis);
  alpha *= holeEdge;

  gl_FragColor = vec4(clamp(col, 0.0, 1.0), alpha);
}
`;

const haloVertSrc = `
varying vec2 vUv;
void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;

const haloFragSrc = `
precision highp float;
#define TAU 6.28318530718

uniform float time;
uniform float bubbleRadius;
varying vec2  vUv;

float h2(vec2 p){ p=fract(p*vec2(234.34,435.345)); p+=dot(p,p+34.23); return fract(p.x*p.y); }
float n2(vec2 p){ vec2 i=floor(p),f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(h2(i),h2(i+vec2(1,0)),u.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),u.x),u.y); }

void main(){
  vec2 uv = vUv * 2.0 - 1.0;
  float r = length(uv);
  if (r > 1.0) discard;

  vec3 colInner   = vec3(0.85, 0.82, 0.95);
  vec3 colMid     = vec3(0.78, 0.76, 0.92);
  vec3 colOuter   = vec3(0.70, 0.72, 0.88);

  vec3 col;
  if (r < 0.45) {
    float t = r / 0.45;
    t = t * t;
    col = mix(colInner, colMid, t);
  } else {
    float t = (r - 0.45) / 0.55;
    t = smoothstep(0.0, 1.0, t);
    col = mix(colMid, colOuter, t);
  }

  float angle = atan(uv.y, uv.x) / TAU;
  float shimmer = n2(vec2(angle * 6.0 + time * 0.04, r * 3.0)) * 0.5 + 0.5;
  float shimBand = smoothstep(0.5, 0.7, r) * (1.0 - smoothstep(0.85, 1.0, r));
  col += vec3(0.80, 0.75, 0.95) * shimmer * shimBand * 0.10;

  float alpha = smoothstep(0.10, 0.55, r) * (1.0 - smoothstep(0.80, 1.00, r)) * 0.30;
  gl_FragColor = vec4(col * alpha, alpha);
}
`;

// ── Sky dome — soft pastel blob gradient (matching p5.js piece aesthetic) ──
const skyVertSrc = `
varying vec3 vDir;
void main() {
    vDir = normalize(position);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const skyFragSrc = `
precision highp float;
#define TAU 6.28318530718
uniform float time;

varying vec3 vDir;

vec3 hsb2rgb(float h, float s, float b) {
    h = fract(h / 360.0);
    vec3 rgb = clamp(abs(fract(h + vec3(0.0,2.0,4.0)/6.0)*6.0-3.0)-1.0, 0.0,1.0);
    return b * mix(vec3(1.0), rgb, s);
}

float blob(vec3 dir, vec3 centre, float r) {
    float d = length(dir - centre);
    return exp(-4.0 * d * d / (r * r));
}

float drift(float seed, float t) {
    return sin(t * 0.11 + seed * TAU) * 0.18 + cos(t * 0.07 + seed * 2.1) * 0.12;
}

void main() {
    vec3 d = normalize(vDir);

    float T       = time * 0.4;
    float baseHue = 240.0 + T * 8.0;

    vec3  bg = hsb2rgb(baseHue, 0.05, 0.97);

    float blobHue  = baseHue + 120.0;
    float blobSat  = 0.60;
    float blobBri  = 1.00;

    vec3 bCentres[5];
    float seeds[5];
    seeds[0] = 0.13; seeds[1] = 0.37; seeds[2] = 0.61;
    seeds[3] = 0.79; seeds[4] = 0.97;

    float totalW = 0.0;
    vec3  totalC = vec3(0.0);

    for (int i = 0; i < 5; i++) {
        float s = seeds[i];
        float phi   = s * TAU;
        float theta = s * 2.83 - 0.9;
        vec3 base   = vec3(cos(theta)*cos(phi), sin(theta), cos(theta)*sin(phi));

        float dx = drift(s,        T + float(i)*0.4);
        float dy = drift(s + 0.5,  T + float(i)*0.7);
        float dz = drift(s + 0.25, T + float(i)*0.55);
        vec3  centre = normalize(base + vec3(dx, dy, dz) * 0.35);

        float hOff = float(i) * 28.0;
        float sz   = 0.55 + s * 0.40;

        float w = blob(d, centre, sz);
        totalC += w * hsb2rgb(blobHue + hOff, blobSat, blobBri);
        totalW += w;
    }

    float blobAlpha = clamp(totalW, 0.0, 1.0);
    vec3  blobCol   = totalW > 0.001 ? totalC / totalW : bg;

    blobAlpha = smoothstep(0.0, 0.85, blobAlpha) * 0.72;

    vec3 col = mix(bg, blobCol, blobAlpha);

    float vig = 1.0 - 0.08 * (1.0 - abs(d.y));
    col *= vig;

    gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

const reflTexMatrix = new THREE.Matrix4();
const reflClipPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const _tmpCamPos = new THREE.Vector3();
const _tmpForward = new THREE.Vector3();
const _tmpLookTarget = new THREE.Vector3();

const spiritVertSrc = `
precision highp float;
uniform float time;
attribute float spiritPhase;
attribute float spiritSize;
varying float vAlpha;

void main() {
  vec3 pos = position;
  float pulse = 0.5 + 0.5 * sin(time * 0.7 + spiritPhase);
  pos.y += sin(time * 0.25 + spiritPhase * 0.7) * 0.04;
  vAlpha = pow(pulse, 1.8) * 0.35;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = max(spiritSize * 240.0 / -mv.z, 1.0);
  gl_Position = projectionMatrix * mv;
}
`;

const spiritFragSrc = `
precision highp float;
varying float vAlpha;

void main() {
  vec2 uv = gl_PointCoord - vec2(0.5);
  float dist = length(uv);
  if (dist > 0.5) discard;
  float edge = 1.0 - smoothstep(0.18, 0.5, dist);
  vec3 col = vec3(0.70, 0.56, 0.96);
  gl_FragColor = vec4(col, vAlpha * edge);
}
`;

/**
 * Temporary compatibility wrapper.
 * Keeps app.js unchanged while replacing the tree point cloud with
 * the bubble sphere shader object from frame_bubble (1).html.
 */
export async function loadPointCloud(_url, options = {}) {
  const onProgress = options.onProgress ?? null;
  if (onProgress) {
    onProgress({ lengthComputable: true, loaded: 1, total: 1 });
  }

  const radius = 0.35;
  const shellThick = 0.035;
  const openAngle = 70.0;

  const mkUniforms = (shellRole) => ({
    time: uniforms.time,
    bubbleRadius: { value: radius },
    shellThick: { value: shellThick },
    sphereAudioLevel: uniforms.sphereAudioLevel,
    sphereAudioTimbre: uniforms.sphereAudioTimbre,
    shellRole: { value: shellRole },
    openAngle: { value: openAngle },
    frameBrightness: { value: 1.0 },
    emissiveStrength: { value: 2.5 },
  });

  const outerMat = new THREE.ShaderMaterial({
    uniforms: mkUniforms(1.0),
    vertexShader: frameVertSrc,
    fragmentShader: outerFragSrc,
    side: THREE.FrontSide,
    transparent: false,
    depthWrite: true,
  });

  const innerMat = new THREE.ShaderMaterial({
    uniforms: mkUniforms(0.0),
    vertexShader: frameVertSrc,
    fragmentShader: innerFragSrc,
    side: THREE.BackSide,
    transparent: false,
    depthWrite: true,
  });

  const group = new THREE.Group();
  group.add(new THREE.Mesh(new THREE.SphereGeometry(radius, 128, 96), outerMat));
  group.add(new THREE.Mesh(new THREE.SphereGeometry(radius - shellThick, 128, 96), innerMat));
  group.name = 'bubble-sphere';
  group.frustumCulled = false;

  console.log('[BubbleSphere] Created shader sphere from frame_bubble source');

  return {
    points: group,
    geometry: null,
    material: [outerMat, innerMat],
    floorOffset: 0.0,
  };
}

export function createBubbleOceanEnvironment() {
  const bubbleRadius = 0.35;
  const oceanY = 0.0;

  const oceanGeo = new THREE.PlaneGeometry(40, 40, 220, 220);
  oceanGeo.rotateX(-Math.PI / 2);

  const oceanMat = new THREE.ShaderMaterial({
    uniforms: {
      time: uniforms.time,
      bubbleRadius: { value: bubbleRadius },
      uReflection: { value: null },
      uReflectMatrix: { value: new THREE.Matrix4() },
    },
    vertexShader: oceanVertSrc,
    fragmentShader: oceanFragSrc,
    transparent: true,
    depthWrite: true,
    side: THREE.FrontSide,
  });

  const oceanMesh = new THREE.Mesh(oceanGeo, oceanMat);
  oceanMesh.position.y = oceanY;
  oceanMesh.frustumCulled = false;

  const haloGeo = new THREE.CircleGeometry(bubbleRadius * 14.0, 192);
  haloGeo.rotateX(-Math.PI / 2);
  const haloMat = new THREE.ShaderMaterial({
    uniforms: {
      time: uniforms.time,
      bubbleRadius: { value: bubbleRadius },
    },
    vertexShader: haloVertSrc,
    fragmentShader: haloFragSrc,
    transparent: true,
    depthWrite: false,
    blending: THREE.NormalBlending,
    side: THREE.FrontSide,
  });

  const haloMesh = new THREE.Mesh(haloGeo, haloMat);
  haloMesh.position.y = oceanY + 0.015;
  haloMesh.frustumCulled = false;

  const reflTarget = new THREE.WebGLRenderTarget(1024, 1024, {
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    format: THREE.RGBAFormat,
  });
  const reflCam = new THREE.PerspectiveCamera();
  oceanMat.uniforms.uReflection.value = reflTarget.texture;

  // ── Sky dome ────────────────────────────────────────────────────────────
  const skyGeo = new THREE.SphereGeometry(50, 48, 24);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    depthTest: false,
    uniforms: { time: uniforms.time },
    vertexShader: skyVertSrc,
    fragmentShader: skyFragSrc,
  });
  const skyMesh = new THREE.Mesh(skyGeo, skyMat);
  skyMesh.renderOrder = -1000;
  skyMesh.frustumCulled = false;

  const envGroup = new THREE.Group();
  envGroup.name = 'bubble-ocean-environment';
  envGroup.add(skyMesh);
  envGroup.add(oceanMesh);

  envGroup.userData.updateReflection = (renderer, scene, camera) => {
    if (!renderer || !scene || !camera) return;

    const activeCamera = renderer.xr.isPresenting ? renderer.xr.getCamera(camera) : camera;

    _tmpCamPos.setFromMatrixPosition(activeCamera.matrixWorld);
    activeCamera.getWorldDirection(_tmpForward);
    _tmpLookTarget.copy(_tmpCamPos).add(_tmpForward);

    reflCam.position.copy(_tmpCamPos);
    reflCam.position.y = 2.0 * oceanY - _tmpCamPos.y;

    const mirroredTarget = _tmpLookTarget.clone();
    mirroredTarget.y = 2.0 * oceanY - mirroredTarget.y;
    reflCam.up.set(0, 1, 0);
    reflCam.lookAt(mirroredTarget);
    reflCam.projectionMatrix.copy(activeCamera.projectionMatrix);
    reflCam.updateMatrixWorld(true);

    reflTexMatrix.set(
      0.5, 0,   0,   0.5,
      0,   0.5, 0,   0.5,
      0,   0,   0.5, 0.5,
      0,   0,   0,   1.0
    );
    reflTexMatrix.multiply(reflCam.projectionMatrix);
    reflTexMatrix.multiply(reflCam.matrixWorldInverse);
    oceanMat.uniforms.uReflectMatrix.value.copy(reflTexMatrix);

    reflClipPlane.set(new THREE.Vector3(0, 1, 0), -oceanY);
    const prevClippingPlanes = renderer.clippingPlanes;
    const prevTarget = renderer.getRenderTarget();
    const prevXrEnabled = renderer.xr.enabled;

    renderer.clippingPlanes = [reflClipPlane];
    renderer.xr.enabled = false;
    oceanMesh.visible = false;

    try {
      renderer.setRenderTarget(reflTarget);
      renderer.clear();
      renderer.render(scene, reflCam);
    } finally {
      renderer.setRenderTarget(prevTarget);
      renderer.xr.enabled = prevXrEnabled;
      renderer.clippingPlanes = prevClippingPlanes;
      oceanMesh.visible = true;
    }
  };

  envGroup.userData.dispose = () => {
    reflTarget.dispose();
    oceanGeo.dispose();
    skyGeo.dispose();
    oceanMat.dispose();
    skyMat.dispose();
  };

  return envGroup;
}

export function createSpiritFireflies(count = 90) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const phase = new Float32Array(count);
  const size = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    const i3 = i * 3;
    const r = 2.4 + Math.random() * 4.8;
    const a = Math.random() * Math.PI * 2.0;
    pos[i3] = Math.cos(a) * r;
    pos[i3 + 1] = 1.0 + Math.random() * 2.2;
    pos[i3 + 2] = Math.sin(a) * r;
    phase[i] = Math.random() * Math.PI * 2.0;
    size[i] = 0.016 + Math.random() * 0.026;
  }

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('spiritPhase', new THREE.BufferAttribute(phase, 1));
  geo.setAttribute('spiritSize', new THREE.BufferAttribute(size, 1));

  const mat = new THREE.ShaderMaterial({
    uniforms: {
      time: uniforms.time,
    },
    vertexShader: spiritVertSrc,
    fragmentShader: spiritFragSrc,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const spirits = new THREE.Points(geo, mat);
  spirits.name = 'spirit-fireflies';
  spirits.frustumCulled = false;
  return spirits;
}

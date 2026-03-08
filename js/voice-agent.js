// voice-agent.js — EEG bridge for WebXR
// Connects to agents/server.py via WebSocket, receives EEG state,
// and exposes it for display in the VR scene.

// ═══════════════════════════════════════════════════════════
// EEG STATE
// ═══════════════════════════════════════════════════════════

let eegState = null;
let eegConnected = false;
let eegWs = null;
const EEG_WS_URL = 'ws://localhost:8765';

// ═══════════════════════════════════════════════════════════
// CALLBACKS (set by app.js)
// ═══════════════════════════════════════════════════════════

const callbacks = {
  onEegUpdate: null,       // (eegState) => void
  onEegConnected: null,    // (connected) => void
};

export function on(event, fn) {
  if (event in callbacks) callbacks[event] = fn;
}

// ═══════════════════════════════════════════════════════════
// EEG WEBSOCKET BRIDGE
// ═══════════════════════════════════════════════════════════

export function connectEeg(url) {
  const wsUrl = url || EEG_WS_URL;
  if (eegWs && eegWs.readyState <= 1) return;

  console.log('[EEG] Connecting to bridge:', wsUrl);
  eegWs = new WebSocket(wsUrl);

  eegWs.onopen = () => {
    eegConnected = true;
    eegWs.send(JSON.stringify({ type: 'register_voice' }));
    console.log('[EEG] Bridge connected');
    callbacks.onEegConnected?.(true);
  };

  eegWs.onclose = () => {
    eegConnected = false;
    console.log('[EEG] Bridge disconnected');
    callbacks.onEegConnected?.(false);
    setTimeout(() => connectEeg(wsUrl), 3000);
  };

  eegWs.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.vad && data.relational_states) {
        eegState = data;
        callbacks.onEegUpdate?.(data);
      }
    } catch { /* ignore */ }
  };

  eegWs.onerror = (err) => {
    console.warn('[EEG] WS error:', err);
  };
}

export function injectSimState(name) {
  if (eegWs?.readyState === WebSocket.OPEN) {
    eegWs.send(JSON.stringify({ type: 'set_sim_state', name }));
  }
}

export function getEegState() { return eegState; }
export function isEegConnected() { return eegConnected; }

// ═══════════════════════════════════════════════════════════
// EEG → EMOTION COLOUR
// ═══════════════════════════════════════════════════════════

/**
 * Map EEG state to an RGBA emotion colour.
 * Default (no data): transparent white {r:255, g:255, b:255, a:0.15}
 *
 * Colour logic (driven by VAD + relational states):
 *   Calm/relaxed   → soft blue     (high valence, low arousal)
 *   Anxious/stress → warm red      (low valence, high arousal)
 *   Engaged/flow   → bright green  (high valence, high arousal)
 *   Confused       → purple        (low valence, low arousal, high confusion)
 *   Trust          → warm gold     (high trust, high comfort)
 *
 * Alpha intensity tracks overall engagement level.
 */
export function eegToColor(eeg) {
  if (!eeg) return { r: 255, g: 255, b: 255, a: 0.15 };

  const valence = eeg.vad.valence;        // -1 … +1
  const arousal = eeg.vad.arousal;         // -1 … +1
  const comfort = eeg.relational_states.comfort;       // 0 … 1
  const engagement = eeg.relational_states.engagement;  // 0 … 1
  const confusion = eeg.relational_states.confusion ?? 0;
  const trust = eeg.relational_states.trust ?? 0;

  // Start with white
  let r = 255, g = 255, b = 255;

  // Blend towards emotion colours based on VAD quadrant
  if (valence >= 0 && arousal < 0) {
    // Positive-calm → soft blue
    const t = Math.min(1, (valence + Math.abs(arousal)) * 0.8);
    r = lerp(255, 100, t);
    g = lerp(255, 180, t);
    b = lerp(255, 255, t);
  } else if (valence < 0 && arousal >= 0) {
    // Negative-aroused → warm red (anxious)
    const t = Math.min(1, (Math.abs(valence) + arousal) * 0.7);
    r = lerp(255, 255, t);
    g = lerp(255, 80, t);
    b = lerp(255, 60, t);
  } else if (valence >= 0 && arousal >= 0) {
    // Positive-aroused → bright green (engaged/flow)
    const t = Math.min(1, (valence + arousal) * 0.6);
    r = lerp(255, 50, t);
    g = lerp(255, 230, t);
    b = lerp(255, 100, t);
  } else {
    // Negative-calm → purple (confused/withdrawn)
    const t = Math.min(1, (Math.abs(valence) + Math.abs(arousal)) * 0.6);
    r = lerp(255, 160, t);
    g = lerp(255, 80, t);
    b = lerp(255, 220, t);
  }

  // Boost confusion → more purple
  if (confusion > 0.4) {
    const ct = (confusion - 0.4) / 0.6;
    r = lerp(r, 140, ct * 0.5);
    g = lerp(g, 60, ct * 0.5);
    b = lerp(b, 200, ct * 0.5);
  }

  // Boost trust → warm gold tint
  if (trust > 0.6) {
    const tt = (trust - 0.6) / 0.4;
    r = lerp(r, 255, tt * 0.3);
    g = lerp(g, 210, tt * 0.3);
    b = lerp(b, 80, tt * 0.3);
  }

  // Alpha: higher engagement = brighter glow (min 0.15, max 0.7)
  const a = 0.15 + engagement * 0.55;

  return { r, g, b, a };
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

// ═══════════════════════════════════════════════════════════
// CLEANUP
// ═══════════════════════════════════════════════════════════

export function dispose() {
  if (eegWs) {
    eegWs.onclose = null;
    eegWs.close();
    eegWs = null;
  }
}

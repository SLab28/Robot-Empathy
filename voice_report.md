# Voice Application Report — slab28-bate-main (GreyMeta)

## Overview

GreyMeta is a **React+Vite+TypeScript** application that runs an **ElevenLabs voice agent** whose tone, pace, and behaviour adapt in real-time to EEG brain-state data. A Three.js orb provides visual feedback. The system supports three personas (Tutor, Workplace, Clinical) and connects to an EEG data source via WebSocket.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  EEG Source (eeg-bridge or eeg-python)                          │
│  WebSocket server on ws://localhost:8765                        │
│  Broadcasts EEG state packets every 1-8 seconds                │
└──────────────────────┬──────────────────────────────────────────┘
                       │ WebSocket
┌──────────────────────▼──────────────────────────────────────────┐
│  React App (app/)                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ EegContext   │→ │ eeg-to-orb   │→ │ OrbCanvas (Three.js)   │ │
│  │ (WS client)  │  │ eeg-to-voice │  │ Reactive sphere        │ │
│  └──────┬──────┘  └──────────────┘  └────────────────────────┘ │
│         │                                                       │
│  ┌──────▼──────────────────────────────────────────────────────┐│
│  │ useElevenLabsAgent hook                                     ││
│  │  - Starts ElevenLabs conversation session                   ││
│  │  - Exposes client tools: get_eeg_state, get_persona,        ││
│  │    show_spotlight_banner, clear_spotlight_banner,            ││
│  │    download_spotlight_card                                   ││
│  │  - Passes dynamic variables from EEG to agent prompt        ││
│  └──────┬──────────────────────────────────────────────────────┘│
│         │                                                       │
│  ┌──────▼──────┐  ┌──────────────────┐                         │
│  │ AgentOverlay │  │ PersonaSelector   │                        │
│  │ - VAD readout│  │ - Tutor           │                        │
│  │ - State btns │  │ - Workplace       │                        │
│  │ - Talk btn   │  │ - Clinical        │                        │
│  │ - Spotlight  │  └──────────────────┘                         │
│  └─────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. EEG Data Sources

**eeg-bridge/** (Node.js, `ws` library)
- WebSocket server on port 8765
- Two modes: `simulate` (cycles calm→anxious→engaged every 8s) and `hardware` (relays external EEG)
- Supports `set_sim_state` and `inject_state` commands from clients
- Sim states: `sim/calm.json`, `sim/anxious.json`, `sim/engaged.json`

**eeg-python/** (Python, `aiohttp`)
- Alternative WebSocket server at `ws://localhost:8765/ws`
- Rotates through 8 rich state packets at configurable interval (default 1s)
- 8 packets: calm, anxious, engaged, confused, focused, tired, trust_building, peak_flow
- Supports `cmd: stop/start` to pause/resume streaming
- Comprehensive test suite (`test_server.py`) validating packet schema

### 2. EEG State Packet Schema (eeg-schema.json + packets)

The **canonical packet format** consumed by the voice app:

| Field | Description |
|---|---|
| `timestamp` | Unix seconds |
| `session_elapsed_seconds` | Time since session start |
| `eeg_features` | `alpha_beta_ratio`, `frontal_asymmetry`, `frontal_theta`, `fronto_temporal_coherence`, `tension_proxy`, `composite_score`, `trajectory` |
| `vad` | `valence` (-1 to 1), `arousal` (-1 to 1), `dominance` (-1 to 1), `quadrant` |
| `relational_states` | `comfort`, `calm`, `trust`, `engagement`, `confusion` (all 0-1) |
| `nlp_emotion_map` | `primary_labels[]`, `secondary_labels[]`, `absent_states[]`, polarity/level |
| `trajectory_interpretation` | `current_direction`, `rate`, `stability`, `notable_event` |
| `specialist_notes` | `prefrontal`, `valence`, `load`, `network` (narrative strings) |
| `rl_agent` | `recommended_action` (int), `action_label` (string), `q_values[4]`, `exploration_rate`, `sessions_in_state_bucket` |
| `voice_direction` | `tone`, `pace` (slow/moderate/fast), `register`, `pitch_variation`, `suggested_opening`, `avoid[]` |

**This is the exact same format as `sample_voice_output.json`** — the agents pipeline output in our system should match this schema so the voice app can consume it directly.

### 3. React App (app/src/)

**Entry: App.tsx**
- Wraps in `PersonaProvider` + `EegProvider`
- Shows `PersonaSelector` first, then `MainScene` (Orb + AgentOverlay)

**EegContext.tsx** — WebSocket client
- Connects to `VITE_EEG_WS_URL` (default `ws://localhost:8765`)
- Parses incoming JSON as `EegState` (vad, relational_states, voice_direction, rl_agent)
- Exposes `injectState('calm'|'anxious'|'engaged')` to send sim state commands
- **Important**: Accepts raw EEG state packets — expects the eeg-schema.json format at minimum (vad, relational_states, voice_direction, rl_agent)

**PersonaContext.tsx** — Persona selection
- Three personas loaded from env vars:
  - **Tutor** (agent_4301..., voice: Daniel) — calm, encouraging, adaptive pacing
  - **Workplace** (agent_5801..., voice: XrExE9yKIg1WjnnlVkGX) — professional, engagement-aware
  - **Clinical** (agent_4901..., voice: Lily) — warm, empathetic, comfort-first
- Each has: `agentId`, `voiceId`, `systemPromptHint`, `color`, `orbColor`

**useElevenLabsAgent.ts** — ElevenLabs conversation hook
- Uses `@elevenlabs/react` `useConversation`
- **Client tools** (callable by the ElevenLabs agent during conversation):
  - `get_eeg_state` → returns live VAD, relational states, voice direction, RL action
  - `get_persona` → returns current persona id/label/hint
  - `show_spotlight_banner` → renders a spotlight overlay with names (demo feature)
  - `clear_spotlight_banner` → hides the spotlight
  - `download_spotlight_card` → generates and downloads a PNG card
- **Dynamic variables** passed into agent prompt: `eeg_tone`, `eeg_pace`, `eeg_register`, `eeg_avoid`, `eeg_valence`, `eeg_arousal`, `eeg_comfort`, `eeg_engagement`, `eeg_action`, `persona`
- Uses refs to always give the agent the latest EEG state without re-registering tools

**eeg-to-voice.ts** — Maps EegState to dynamic variable dict for agent prompt injection

**eeg-to-orb.ts** — Maps EegState to OrbParams:
- `speed` ← arousal (high arousal = faster rotation)
- `radius` ← comfort (high comfort = larger orb)
- `opacity` ← valence (positive = brighter)
- `pulseRate` ← arousal (high = faster pulse)
- `emissiveIntensity` ← engagement

**OrbCanvas.tsx** — Three.js sphere with wireframe overlay
- Reacts in real-time to EEG-derived orb params
- Color matches persona (`orbColor`)

**AgentOverlay.tsx** — HUD overlay
- Shows EEG readout (VAD values, comfort/engagement %, tone/pace)
- State injection buttons (calm/anxious/engaged) for demo
- Start/End Session button (toggles ElevenLabs conversation)
- Speaking/Listening indicator
- Spotlight banner overlay (triggered by agent client tool)

### 4. ElevenLabs Agent Configuration

Each agent's system prompt instructs it to:
1. **Silently call `get_eeg_state`** at the start of each response
2. **Adapt behavior** based on:
   - High arousal (>0.5) → slow down, simplify
   - Low engagement (<0.4) → ask curious questions
   - Low comfort (<0.4) → be reassuring
   - Always match `tone`, `pace`, `register` from EEG data
   - Always respect `avoid` list
3. Use dynamic variables in prompt template: `{{eeg_tone}}`, `{{eeg_pace}}`, etc.

---

## Integration Point with Our Agent Pipeline

### Current gap
Our `agents/server.py` pipeline produces `voice_output_*.json` files in the `sample_voice_output.json` format. The GreyMeta voice app consumes EEG state packets from a WebSocket. These schemas **are the same format**.

### Integration path
To connect our agent pipeline output to the voice app:
1. Our `server.py` already saves `voice_output` JSON with the correct schema fields (vad, relational_states, voice_direction, rl_agent, eeg_features, etc.)
2. The voice app's `EegContext.tsx` connects to `ws://localhost:8765` and expects packets with at minimum: `vad`, `relational_states`, `voice_direction`, `rl_agent`
3. **Our server already runs on ws://localhost:8765** — we need to broadcast the `voice_output` as a top-level message (not nested inside a `pipeline_result` type) so the voice app can consume it
4. Alternatively, the voice app can connect to our server and we add a message type that the EegContext recognizes

### Required fields for voice app (minimum)
```json
{
  "vad": { "valence": float, "arousal": float, "dominance": float },
  "relational_states": { "comfort": float, "calm": float, "trust": float, "engagement": float, "confusion": float },
  "voice_direction": { "tone": string, "pace": "slow|moderate|fast", "register": string, "avoid": [strings] },
  "rl_agent": { "recommended_action": int, "action_label": string, "q_values": [4 floats] }
}
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `VITE_ELEVENLABS_API_KEY` | ElevenLabs API key |
| `VITE_EEG_WS_URL` | EEG WebSocket URL (default `ws://localhost:8765`) |
| `VITE_TUTOR_AGENT_ID` | ElevenLabs agent ID for tutor persona |
| `VITE_TUTOR_VOICE_ID` | Voice ID for tutor |
| `VITE_WORKPLACE_AGENT_ID` | ElevenLabs agent ID for workplace persona |
| `VITE_WORKPLACE_VOICE_ID` | Voice ID for workplace |
| `VITE_CLINICAL_AGENT_ID` | ElevenLabs agent ID for clinical persona |
| `VITE_CLINICAL_VOICE_ID` | Voice ID for clinical |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `@elevenlabs/react` | ^0.14.1 | ElevenLabs conversational AI SDK |
| `three` | ^0.183.2 | Three.js for orb rendering |
| `react` | ^19.2.0 | UI framework |
| `vite` | ^7.3.1 | Build tool |
| `aiohttp` | (eeg-python) | Python WebSocket server |
| `ws` | ^8.18.0 | (eeg-bridge) Node.js WebSocket |

---

## File Map

```
slab28-bate-main/
├── app/                          ← React+Vite voice agent frontend
│   ├── src/
│   │   ├── App.tsx               ← Entry: PersonaProvider > EegProvider > Selector/MainScene
│   │   ├── main.tsx              ← ReactDOM render
│   │   ├── components/
│   │   │   ├── PersonaSelector   ← 3-persona selection screen (tutor/workplace/clinical)
│   │   │   ├── MainScene.tsx     ← Orb + AgentOverlay composition
│   │   │   ├── OrbCanvas.tsx     ← Three.js EEG-reactive sphere
│   │   │   └── AgentOverlay.tsx  ← HUD: VAD readout, state buttons, talk button, spotlight
│   │   ├── contexts/
│   │   │   ├── EegContext.tsx    ← WS client receiving EEG state packets
│   │   │   └── PersonaContext    ← Persona state management
│   │   ├── hooks/
│   │   │   └── useElevenLabsAgent.ts ← ElevenLabs hook with 5 client tools
│   │   └── lib/
│   │       ├── eeg-to-orb.ts    ← VAD/relational → orb visual params
│   │       └── eeg-to-voice.ts  ← EegState → agent dynamic variables
│   ├── .env.example             ← Required env vars template
│   ├── .env.local               ← Actual keys (gitignored)
│   └── package.json             ← @elevenlabs/react, three, react
├── eeg-bridge/                   ← Node.js WS server (sim/hardware modes)
│   ├── server.js                ← WS broadcast, 8s sim cycle, set_sim_state cmd
│   └── sim/                     ← 3 state JSONs (calm, anxious, engaged)
├── eeg-python/                   ← Python WS server (8 rich state packets)
│   ├── server.py                ← aiohttp WS, 1s rotation, stop/start cmds
│   ├── packets/                 ← 8 JSON packets (calm→peak_flow)
│   ├── test_server.py           ← Comprehensive schema + server tests
│   └── test.html                ← Browser test UI
├── shared/
│   ├── personas.json            ← 3 persona definitions with agent/voice IDs
│   └── eeg-schema.json          ← Canonical EEG packet field spec
└── docs/
    ├── agents/                  ← ElevenLabs agent configs (system prompts, tool IDs)
    └── plans/                   ← Build plan (greymeta-build.md)
```

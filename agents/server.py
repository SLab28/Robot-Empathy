"""
Empathetic Robot Framework — Affective Computing Server
========================================================
WebSocket server that orchestrates 4 specialized Claude agents
coordinated by a Master Neuroscientist agent for real-time
affective computing from EEG data.

Architecture:
  WebSocket ←→ Agent Pipeline
                    │
        ┌───────────┼────────────────┐
        ▼           ▼                ▼
   [EEG Agent]  [Context Agent]      │
        │           │                │
        └─────┬─────┘                │
              ▼                      │
       [Affective Agent]             │
              │                      │
              ▼                      ▼
       [Master Neuroscientist Agent]
              │
              ▼
       Downstream (Robot / RL / WebXR)

Agents:
  1. EEG Agent — Signal processing & feature extraction → EEGFeatureEvidenceV1
  2. Context Agent — Behavioral & environmental monitoring → ContextContaminationStateV1
  3. Affective Agent — Emotional state synthesis → AffectiveStateV1
  4. Master Neuroscientist — Output auditing & gating → NeuroscienceReviewV1
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import logging
import os
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import websockets
import anthropic
import numpy as np
import threading
import time as _time

# Optional: pylsl for live Muse EEG streaming
try:
    from pylsl import StreamInlet, resolve_byprop as lsl_resolve
    LSL_AVAILABLE = True
except ImportError:
    LSL_AVAILABLE = False

# Add data module to path
DATA_MODULE_DIR = Path(__file__).parent / "data" / "data_preprocessed_python-001"
sys.path.insert(0, str(DATA_MODULE_DIR))

from deap_loader import DEAPLoader, DEAPTrial, DEAP_CHANNEL_MAPPING
from deap_simulator import DEAPSimulator, EEGWindow
from eeg_feature_extraction import EEGFeatureExtractor, FeatureExtractionConfig

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL            = os.environ.get("EMPATHY_MODEL", "claude-sonnet-4-6")
WS_HOST          = os.environ.get("WS_HOST", "localhost")
WS_PORT          = int(os.environ.get("WS_PORT", "8765"))

AGENTS_DIR = Path(__file__).parent  # directory containing the .md files
DEAP_DATA_DIR = DATA_MODULE_DIR / "data_preprocessed_python"
OUTPUT_DIR   = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("empathy")

# ═══════════════════════════════════════════════════════════════
# LOAD AGENT SKILL & RULES FROM .md FILES
# ═══════════════════════════════════════════════════════════════

def _load_md(filename: str) -> str:
    """Load a markdown file from the agents directory."""
    path = AGENTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    log.warning(f"Agent file not found: {path}")
    return ""

SYSTEM_RULES       = _load_md("00_system_orchestration_RULES.md")
EEG_SKILL          = _load_md("01_eeg_agent_SKILL.md")
EEG_RULES          = _load_md("02_eeg_agent_RULES.md")
AFFECTIVE_SKILL    = _load_md("03_affective_agent_SKILL.md")
AFFECTIVE_RULES    = _load_md("04_affective_agent_RULES.md")
CONTEXT_SKILL      = _load_md("05_context_agent_SKILL.md")
CONTEXT_RULES      = _load_md("06_context_agent_RULES.md")
MASTER_SKILL       = _load_md("07_master_neuroscientist_SKILL.md")
MASTER_RULES       = _load_md("08_master_neuroscientist_RULES.md")

# ═══════════════════════════════════════════════════════════════
# AGENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════

@dataclass
class Agent:
    id: str
    name: str
    role: str
    canonical_output: str
    system_prompt: str
    max_tokens: int = 1500

AGENTS = {}

AGENTS["eeg"] = Agent(
    id="eeg",
    name="EEG Signal Analysis Specialist",
    role="Signal processing & feature extraction",
    canonical_output="EEGFeatureEvidenceV1",
    max_tokens=2000,
    system_prompt=f"""You are the EEG Signal Analysis & Visualization Specialist in the Empathetic Robot Framework.

{SYSTEM_RULES}

--- YOUR SKILL ---
{EEG_SKILL}

--- YOUR RULES ---
{EEG_RULES}

You must respond with a valid JSON object conforming to the EEGFeatureEvidenceV1 schema defined in your RULES.
Include the full envelope (schema_name, message_id, session_id, etc.) and the required payload (quality, features, trajectory, engineering_notes).
Do not include any text outside the JSON object."""
)

AGENTS["context"] = Agent(
    id="context",
    name="Context, Clinical & Contamination Agent",
    role="Behavioral & environmental monitoring",
    canonical_output="ContextContaminationStateV1",
    max_tokens=1500,
    system_prompt=f"""You are the Context, Clinical & Contamination Agent in the Empathetic Robot Framework.

{SYSTEM_RULES}

--- YOUR SKILL ---
{CONTEXT_SKILL}

--- YOUR RULES ---
{CONTEXT_RULES}

You must respond with a valid JSON object conforming to the ContextContaminationStateV1 schema defined in your RULES.
Include the full envelope and the required payload (context_state, contamination_report, upstream_notes).
Do not include any text outside the JSON object."""
)

AGENTS["affective"] = Agent(
    id="affective",
    name="Affective Computing Specialist",
    role="Emotional state synthesis",
    canonical_output="AffectiveStateV1",
    max_tokens=2000,
    system_prompt=f"""You are the Affective Computing Specialist in the Empathetic Robot Framework.

{SYSTEM_RULES}

--- YOUR SKILL ---
{AFFECTIVE_SKILL}

--- YOUR RULES ---
{AFFECTIVE_RULES}

You must respond with a valid JSON object conforming to the AffectiveStateV1 schema defined in your RULES.
Include the full envelope and the required payload (vad, relational, nlp_map, modality_reconciliation, interpretation, recommendation, limits, review_status).
Do not include any text outside the JSON object."""
)

AGENTS["master"] = Agent(
    id="master",
    name="Master Neuroscientist Orchestrator",
    role="Output auditing & gating",
    canonical_output="NeuroscienceReviewV1",
    max_tokens=1500,
    system_prompt=f"""You are the Master Neuroscientist Orchestrator in the Empathetic Robot Framework.

{SYSTEM_RULES}

--- YOUR SKILL ---
{MASTER_SKILL}

--- YOUR RULES ---
{MASTER_RULES}

You must respond with a valid JSON object conforming to the NeuroscienceReviewV1 schema defined in your RULES.
Include the full envelope and the required payload (review_status, priority, issues, confidence_adjustments, workflow_changes, global_instruction, release_gate).
Do not include any text outside the JSON object."""
)

# ═══════════════════════════════════════════════════════════════
# ANTHROPIC CLIENT
# ═══════════════════════════════════════════════════════════════

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ═══════════════════════════════════════════════════════════════
# DEAP SIMULATOR & FEATURE EXTRACTION
# ═══════════════════════════════════════════════════════════════

feature_extractor = EEGFeatureExtractor(FeatureExtractionConfig(
    sampling_rate=128,
    window_size_seconds=4.0,
))

# Per-client simulator state
_client_simulators: dict = {}  # websocket -> { simulator, task, last_features }

# ═══════════════════════════════════════════════════════════════
# VOICE APP BRIDGE
# ═══════════════════════════════════════════════════════════════

# Voice app clients registered via {type: "register_voice"}
_voice_clients: set = set()  # set of websocket objects
_latest_voice_state: dict = {}  # last broadcast EEG state packet

# Prebuilt sim states for voice app demo injection buttons
_SIM_STATES = {
    "calm": {
        "timestamp": 0,
        "vad": {"valence": 0.61, "arousal": -0.38, "dominance": 0.44, "quadrant": "positive_calm_controlled"},
        "relational_states": {"comfort": 0.74, "calm": 0.69, "trust": 0.61, "engagement": 0.55, "confusion": 0.08},
        "voice_direction": {"tone": "warm_settled", "pace": "slow", "register": "affirming_curious", "pitch_variation": "low", "suggested_opening": "Gentle affirmation", "avoid": ["urgency", "high_energy"]},
        "rl_agent": {"recommended_action": 1, "action_label": "calm_neutral_curious", "q_values": [0.31, 0.68, 0.42, 0.19], "exploration_rate": 0.12, "sessions_in_state_bucket": 7},
    },
    "anxious": {
        "timestamp": 0,
        "vad": {"valence": -0.3, "arousal": 0.72, "dominance": 0.21},
        "relational_states": {"comfort": 0.22, "calm": 0.18, "trust": 0.41, "engagement": 0.63, "confusion": 0.55},
        "voice_direction": {"tone": "grounding_calm", "pace": "slow", "register": "reassuring", "pitch_variation": "minimal", "suggested_opening": "Grounding", "avoid": ["urgency", "complexity", "rapid_questions"]},
        "rl_agent": {"recommended_action": 2, "action_label": "grounding_reassurance", "q_values": [0.21, 0.31, 0.67, 0.11], "exploration_rate": 0.1, "sessions_in_state_bucket": 3},
    },
    "engaged": {
        "timestamp": 0,
        "vad": {"valence": 0.72, "arousal": 0.61, "dominance": 0.65},
        "relational_states": {"comfort": 0.71, "calm": 0.55, "trust": 0.78, "engagement": 0.91, "confusion": 0.09},
        "voice_direction": {"tone": "energetic_curious", "pace": "moderate", "register": "collaborative_exploratory", "pitch_variation": "high", "suggested_opening": "Match energy", "avoid": ["repetition", "over_explanation"]},
        "rl_agent": {"recommended_action": 3, "action_label": "explore_challenge", "q_values": [0.28, 0.42, 0.39, 0.71], "exploration_rate": 0.08, "sessions_in_state_bucket": 5},
    },
}


async def _broadcast_voice_state(state: dict):
    """Broadcast an EEG state packet to all registered voice app clients."""
    global _latest_voice_state
    state["timestamp"] = int(datetime.now(timezone.utc).timestamp())
    _latest_voice_state = state
    msg = json.dumps(state, default=str)
    dead = []
    for ws in _voice_clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _voice_clients.discard(ws)
    if _voice_clients:
        log.info(f"Voice state broadcast to {len(_voice_clients)} client(s)")


def _extract_window_features(window: EEGWindow) -> dict:
    """Extract features from an EEGWindow and return a JSON-serializable dict."""
    try:
        features = feature_extractor.extract_features(window.channels)
        feature_dict = features.to_dict()
    except ValueError:
        # Missing channels for some features — extract what we can
        feature_dict = {}
        for method_name in ['frontal_asymmetry', 'alpha_beta_ratio',
                           'frontal_theta_proxy', 'frontotemporal_stability']:
            try:
                val = getattr(feature_extractor, f'extract_{method_name}')(window.channels)
                feature_dict[method_name] = float(val) if val is not None else None
            except Exception:
                feature_dict[method_name] = None

    # Compute per-channel band powers for visualization
    band_powers = {}
    for ch_name in ['Fp1', 'Fp2', 'AF3', 'AF4', 'F3', 'F4', 'F7', 'F8',
                    'C3', 'C4', 'T7', 'T8', 'P3', 'P4', 'O1', 'O2']:
        if ch_name in window.channels:
            try:
                alpha = feature_extractor._compute_band_power(
                    window.channels[ch_name], feature_extractor.config.alpha_band)
                beta = feature_extractor._compute_band_power(
                    window.channels[ch_name], feature_extractor.config.beta_band)
                theta = feature_extractor._compute_band_power(
                    window.channels[ch_name], feature_extractor.config.theta_band)
                band_powers[ch_name] = {
                    "alpha": round(float(alpha), 4),
                    "beta": round(float(beta), 4),
                    "theta": round(float(theta), 4),
                }
            except Exception:
                pass

    return {
        "features": {k: round(float(v), 6) if v is not None else None
                     for k, v in feature_dict.items()},
        "band_powers": band_powers,
        "window_index": window.window_index,
        "start_time": round(window.start_time, 2),
        "end_time": round(window.end_time, 2),
        "channels": list(window.channels.keys()),
        "sampling_rate": window.sampling_rate,
        "metadata": {
            "participant_id": window.metadata.participant_id,
            "trial_id": window.metadata.trial_id,
            "valence": round(float(window.metadata.valence), 2),
            "arousal": round(float(window.metadata.arousal), 2),
            "dominance": round(float(window.metadata.dominance), 2),
            "liking": round(float(window.metadata.liking), 2),
        },
    }


async def _run_deap_stream(simulator: DEAPSimulator, ws, session_id: str):
    """Async loop that polls the threaded simulator and sends windows to the client."""
    loop = asyncio.get_event_loop()
    window_queue: asyncio.Queue = asyncio.Queue()

    def on_window(window: EEGWindow):
        """Called from simulator thread — schedule into async queue."""
        loop.call_soon_threadsafe(window_queue.put_nowait, window)

    simulator.on_window(on_window)
    simulator.start()

    await send(ws, {"type": "deap_status", "status": "playing",
                    "session_id": session_id})

    try:
        while simulator.get_state().value == "playing" or not window_queue.empty():
            try:
                window = await asyncio.wait_for(window_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # Check if simulator finished
                state = simulator.get_state().value
                if state in ("stopped", "idle"):
                    break
                continue

            # Extract features
            feat_data = await loop.run_in_executor(None, _extract_window_features, window)

            # Store last features for on-demand agent analysis
            client_state = _client_simulators.get(id(ws))
            if client_state:
                client_state["last_features"] = feat_data

            # Send to frontend
            await send(ws, {
                "type": "deap_window",
                "session_id": session_id,
                **feat_data,
            })

    except asyncio.CancelledError:
        log.info("DEAP stream cancelled")
    except Exception as e:
        log.error(f"DEAP stream error: {e}")
        await send(ws, {"type": "error", "message": f"DEAP stream error: {e}"})
    finally:
        try:
            simulator.stop()
        except Exception:
            pass
        await send(ws, {"type": "deap_status", "status": "stopped",
                        "session_id": session_id})


# ═══════════════════════════════════════════════════════════════
# LIVE MUSE EEG (via LSL)
# ═══════════════════════════════════════════════════════════════

# Muse 2 / Muse S channels → standard 10-20 proxy mapping for feature extraction
MUSE_CHANNEL_NAMES = ["TP9", "AF7", "AF8", "TP10"]
MUSE_CHANNEL_MAP = {
    # Muse AF7/AF8 are anterior-frontal → proxies for F3/F4, Fp1/Fp2, F7/F8
    "AF7": ["F3", "Fp1", "F7"],
    "AF8": ["F4", "Fp2", "F8"],
    # Muse TP9/TP10 are temporal-parietal → proxies for T7/T8, P3/P4
    "TP9": ["T7", "P3"],
    "TP10": ["T8", "P4"],
}

# Feature extractor tuned for Muse sampling rate (256 Hz)
muse_feature_extractor = EEGFeatureExtractor(FeatureExtractionConfig(
    sampling_rate=256,
    window_size_seconds=4.0,
))

# Per-client live EEG state
_client_muse: dict = {}  # websocket id -> { task, running, last_features, window_index }


def _muse_channels_to_standard(muse_data: dict) -> dict:
    """Map Muse 4-channel data to standard 10-20 channel names for feature extraction."""
    standard = {}
    for muse_ch, proxies in MUSE_CHANNEL_MAP.items():
        if muse_ch in muse_data:
            for proxy in proxies:
                standard[proxy] = muse_data[muse_ch]
    # Also keep original names for band power display
    for ch in MUSE_CHANNEL_NAMES:
        if ch in muse_data:
            standard[ch] = muse_data[ch]
    return standard


def _extract_muse_features(channels: dict, window_index: int, start_time: float) -> dict:
    """Extract features from a Muse EEG window dict and return JSON-serializable data."""
    # Map to standard names
    std_channels = _muse_channels_to_standard(channels)

    # Extract features using the standard-named channels
    feature_dict = {}
    for method_name in ['frontal_asymmetry', 'alpha_beta_ratio',
                        'frontal_theta_proxy', 'frontotemporal_stability']:
        try:
            val = getattr(muse_feature_extractor, f'extract_{method_name}')(std_channels)
            feature_dict[method_name] = float(val) if val is not None else None
        except Exception:
            feature_dict[method_name] = None

    # Band powers for original Muse channels
    band_powers = {}
    for ch_name in MUSE_CHANNEL_NAMES:
        if ch_name in channels:
            try:
                alpha = muse_feature_extractor._compute_band_power(
                    channels[ch_name], muse_feature_extractor.config.alpha_band)
                beta = muse_feature_extractor._compute_band_power(
                    channels[ch_name], muse_feature_extractor.config.beta_band)
                theta = muse_feature_extractor._compute_band_power(
                    channels[ch_name], muse_feature_extractor.config.theta_band)
                band_powers[ch_name] = {
                    "alpha": round(float(alpha), 4),
                    "beta": round(float(beta), 4),
                    "theta": round(float(theta), 4),
                }
            except Exception:
                pass

    end_time = start_time + 4.0
    return {
        "features": {k: round(float(v), 6) if v is not None else None
                     for k, v in feature_dict.items()},
        "band_powers": band_powers,
        "window_index": window_index,
        "start_time": round(start_time, 2),
        "end_time": round(end_time, 2),
        "channels": MUSE_CHANNEL_NAMES,
        "sampling_rate": 256,
        "metadata": {
            "participant_id": "live_muse",
            "source": "muse_lsl",
        },
    }


async def _run_muse_stream(ws, session_id: str):
    """Connect to LSL EEG stream and emit windowed features to the WebSocket client."""
    if not LSL_AVAILABLE:
        await send(ws, {"type": "error", "message": "pylsl not installed. Run: pip install pylsl"})
        return

    loop = asyncio.get_running_loop()
    ws_id = id(ws)
    window_queue: asyncio.Queue = asyncio.Queue()

    # Threaded LSL reader
    stop_event = threading.Event()
    WINDOW_SAMPLES = 256 * 4   # 4 seconds at 256 Hz
    STEP_SAMPLES = 256 * 1     # 1 second step

    def lsl_reader_thread():
        """Read from LSL inlet, buffer into sliding windows, push to async queue."""
        try:
            # Resolve with short retries so we can check stop_event
            log.info("Resolving LSL EEG stream (ensure muselsl is streaming)...")
            streams = None
            for attempt in range(5):
                if stop_event.is_set():
                    return
                log.info(f"  LSL resolve attempt {attempt + 1}/5...")
                streams = lsl_resolve("type", "EEG", timeout=2)
                if streams:
                    break
            if not streams:
                log.warning("No LSL EEG stream found after 5 attempts (10s)")
                loop.call_soon_threadsafe(window_queue.put_nowait,
                    {"error": "No LSL EEG stream found. Start muselsl streaming first."})
                return

            inlet = StreamInlet(streams[0])
            info = inlet.info()
            fs = info.nominal_srate() or 256
            n_ch = min(info.channel_count(), 4)  # Muse has 4 EEG + optional AUX
            log.info(f"LSL connected: {info.name()}, {n_ch} ch @ {fs} Hz")

            loop.call_soon_threadsafe(window_queue.put_nowait,
                                     {"status": "connected", "name": info.name(), "fs": fs})

            # Ring buffer: (channels, samples)
            ring = np.zeros((n_ch, WINDOW_SAMPLES), dtype=np.float64)
            fill = 0  # samples accumulated since last emission
            total_samples = 0
            window_idx = 0

            while not stop_event.is_set():
                samples, timestamps = inlet.pull_chunk(timeout=0.1, max_samples=64)
                if not samples:
                    continue

                data = np.array(samples)[:, :n_ch].T  # (n_ch, chunk_len)
                chunk_len = data.shape[1]

                # Shift ring buffer left and append new data
                if chunk_len >= WINDOW_SAMPLES:
                    ring[:, :] = data[:, -WINDOW_SAMPLES:]
                    fill = WINDOW_SAMPLES
                else:
                    ring[:, :-chunk_len] = ring[:, chunk_len:]
                    ring[:, -chunk_len:] = data
                    fill += chunk_len

                total_samples += chunk_len

                # Emit window when we have enough data and step threshold is reached
                if fill >= STEP_SAMPLES and total_samples >= WINDOW_SAMPLES:
                    fill = 0
                    # Build channel dict
                    ch_data = {}
                    for i, name in enumerate(MUSE_CHANNEL_NAMES[:n_ch]):
                        ch_data[name] = ring[i].copy()

                    start_t = total_samples / fs - 4.0
                    window_idx += 1
                    loop.call_soon_threadsafe(
                        window_queue.put_nowait,
                        {"window": ch_data, "index": window_idx, "start": max(0, start_t)}
                    )

        except Exception as e:
            log.error(f"LSL reader error: {e}")
            loop.call_soon_threadsafe(window_queue.put_nowait, {"error": str(e)})

    reader = threading.Thread(target=lsl_reader_thread, daemon=True)
    reader.start()

    await send(ws, {"type": "muse_status", "status": "connecting", "session_id": session_id})

    try:
        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(window_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                client_state = _client_muse.get(ws_id)
                if not client_state or not client_state.get("running"):
                    break
                continue

            if "error" in msg:
                await send(ws, {"type": "error", "message": msg["error"]})
                break

            if "status" in msg:
                await send(ws, {
                    "type": "muse_status", "status": msg["status"],
                    "session_id": session_id,
                    "stream_name": msg.get("name", ""),
                    "sampling_rate": msg.get("fs", 256),
                })
                continue

            if "window" in msg:
                feat_data = await loop.run_in_executor(
                    None, _extract_muse_features,
                    msg["window"], msg["index"], msg["start"],
                )

                # Store for on-demand analysis
                client_state = _client_muse.get(ws_id)
                if client_state:
                    client_state["last_features"] = feat_data

                await send(ws, {
                    "type": "muse_window",
                    "session_id": session_id,
                    **feat_data,
                })

                # ── Auto-analyze: trigger pipeline at interval ──
                if client_state and client_state.get("auto_analyze"):
                    interval = client_state.get("analyze_interval", 15)
                    now = _time.monotonic()
                    last_run = client_state.get("last_analyze_time", 0)
                    pipeline_busy = client_state.get("pipeline_task") and not client_state["pipeline_task"].done()

                    if not pipeline_busy and (now - last_run) >= interval:
                        client_state["last_analyze_time"] = now
                        pipeline_data = {
                            "session_id": session_id,
                            "participant_id": "live_muse",
                            "eeg_data": {
                                "features": feat_data["features"],
                                "band_powers": feat_data["band_powers"],
                                "window": {
                                    "start_time": feat_data["start_time"],
                                    "end_time": feat_data["end_time"],
                                    "index": feat_data["window_index"],
                                },
                                "channels": feat_data["channels"],
                                "sampling_rate": feat_data["sampling_rate"],
                            },
                            "context_events": {
                                "source": "live_muse_eeg",
                                "phase": "live_recording",
                                "device": "Muse",
                                "auto_analyze": True,
                            },
                            "voice_text": {},
                        }
                        log.info(f"Auto-analyzing live Muse window {feat_data['window_index']}")
                        await send(ws, {"type": "auto_analyze_start",
                                        "window_index": feat_data["window_index"]})
                        ptask = asyncio.create_task(
                            run_affective_pipeline(pipeline_data, ws))
                        client_state["pipeline_task"] = ptask

    except asyncio.CancelledError:
        log.info("Muse stream cancelled")
    except Exception as e:
        log.error(f"Muse stream error: {e}")
        await send(ws, {"type": "error", "message": f"Muse stream error: {e}"})
    finally:
        stop_event.set()
        reader.join(timeout=3)
        await send(ws, {"type": "muse_status", "status": "stopped", "session_id": session_id})


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _make_envelope(agent: Agent, session_id: str, participant_id: str) -> dict:
    """Create a standard envelope for an agent's output."""
    return {
        "schema_name": agent.canonical_output,
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "participant_id": participant_id,
        "producer_agent": agent.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _try_parse_json(text: str) -> Optional[dict]:
    """Attempt to parse JSON from agent response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ═══════════════════════════════════════════════════════════════
# AGENT EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════

async def run_agent(
    agent: Agent,
    user_content: str,
    ws,
    session_id: str = "",
    participant_id: str = "",
) -> dict:
    """Run a single agent with streaming output back to the WebSocket client."""

    await send(ws, {
        "type": "agent_thinking",
        "agent_id": agent.id,
        "agent_name": agent.name,
        "role": agent.role,
    })

    full_response = ""
    buffer = ""

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=agent.max_tokens,
            system=agent.system_prompt,
            messages=[{"role": "user", "content": user_content}]
        ) as stream:

            await send(ws, {
                "type": "agent_speaking",
                "agent_id": agent.id,
                "text": "",
            })

            for text_chunk in stream.text_stream:
                full_response += text_chunk
                buffer += text_chunk

                if len(buffer) >= 30 or text_chunk in "}],":
                    await send(ws, {
                        "type": "agent_speaking",
                        "agent_id": agent.id,
                        "text": full_response,
                    })
                    buffer = ""
                    await asyncio.sleep(0.03)

            # Final flush
            if buffer:
                await send(ws, {
                    "type": "agent_speaking",
                    "agent_id": agent.id,
                    "text": full_response,
                })

    except Exception as e:
        log.error(f"Agent {agent.name} error: {e}")
        full_response = json.dumps({
            "error": str(e),
            "agent": agent.id,
        })
        await send(ws, {
            "type": "agent_speaking",
            "agent_id": agent.id,
            "text": full_response,
        })

    await asyncio.sleep(0.3)
    await send(ws, {"type": "agent_done", "agent_id": agent.id})

    # Try to parse the JSON response
    parsed = _try_parse_json(full_response)
    if parsed is None:
        log.warning(f"Agent {agent.name} did not return valid JSON")
        parsed = {"raw_text": full_response, "parse_error": True}

    return parsed


# ═══════════════════════════════════════════════════════════════
# VOICE OUTPUT FILE (always saved, regardless of release gate)
# ═══════════════════════════════════════════════════════════════

def _deep_get(d: dict, *keys, default=None):
    """Safely traverse nested dicts."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def _compose_voice_output(
    eeg_result: dict,
    context_result: dict,
    affective_result: dict,
    review_result: dict,
    data: dict,
) -> dict:
    """
    Map agent pipeline results into the canonical voice-output JSON format
    (see sample_voice_output.json).  Extracts available fields; missing data
    becomes None so downstream consumers can detect gaps.
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())

    # --- EEG features (from raw DEAP features passed into pipeline, or agent output) ---
    raw_eeg = data.get("eeg_data", {})
    raw_feat = raw_eeg.get("features", {})
    eeg_payload = _deep_get(eeg_result, "payload") or eeg_result

    eeg_features = {
        "alpha_beta_ratio":          raw_feat.get("alpha_beta_ratio")
                                     or _deep_get(eeg_payload, "alpha_beta_ratio"),
        "frontal_asymmetry":         raw_feat.get("frontal_asymmetry")
                                     or _deep_get(eeg_payload, "frontal_asymmetry"),
        "frontal_theta":             raw_feat.get("frontal_theta_proxy")
                                     or _deep_get(eeg_payload, "frontal_theta"),
        "fronto_temporal_coherence":  raw_feat.get("frontotemporal_stability")
                                     or _deep_get(eeg_payload, "fronto_temporal_coherence"),
        "tension_proxy":             _deep_get(eeg_payload, "tension_proxy"),
        "composite_score":           _deep_get(eeg_payload, "composite_score"),
        "trajectory":                _deep_get(eeg_payload, "trajectory"),
    }

    # --- Affective state ---
    aff_payload = _deep_get(affective_result, "payload") or affective_result

    vad_src = _deep_get(aff_payload, "vad") or {}
    vad = {
        "valence":   vad_src.get("valence"),
        "arousal":   vad_src.get("arousal"),
        "dominance": vad_src.get("dominance"),
        "quadrant":  vad_src.get("quadrant"),
    }

    rel_src = _deep_get(aff_payload, "relational") or _deep_get(aff_payload, "relational_states") or {}
    relational_states = {
        "comfort":    rel_src.get("comfort"),
        "calm":       rel_src.get("calm"),
        "trust":      rel_src.get("trust"),
        "engagement": rel_src.get("engagement"),
        "confusion":  rel_src.get("confusion"),
    }

    nlp_src = _deep_get(aff_payload, "nlp_map") or _deep_get(aff_payload, "nlp_emotion_map") or {}
    nlp_emotion_map = {
        "primary_labels":   nlp_src.get("primary_labels", []),
        "secondary_labels": nlp_src.get("secondary_labels", []),
        "absent_states":    nlp_src.get("absent_states", []),
        "valence_polarity": nlp_src.get("valence_polarity"),
        "arousal_level":    nlp_src.get("arousal_level"),
        "dominance_level":  nlp_src.get("dominance_level"),
    }

    traj_src = _deep_get(aff_payload, "interpretation") or _deep_get(aff_payload, "trajectory_interpretation") or {}
    trajectory_interpretation = {
        "current_direction": traj_src.get("current_direction"),
        "rate":              traj_src.get("rate"),
        "stability":         traj_src.get("stability"),
        "notable_event":     traj_src.get("notable_event"),
    }

    # --- Specialist notes (from EEG agent or review) ---
    notes_src = _deep_get(eeg_payload, "specialist_notes") or _deep_get(review_result, "payload", "specialist_notes") or {}
    specialist_notes = {
        "prefrontal": notes_src.get("prefrontal"),
        "valence":    notes_src.get("valence"),
        "load":       notes_src.get("load"),
        "network":    notes_src.get("network"),
    }

    # --- RL agent (from affective recommendation or review) ---
    rl_src = _deep_get(aff_payload, "recommendation") or _deep_get(aff_payload, "rl_agent") or {}
    rl_agent = {
        "recommended_action":      rl_src.get("recommended_action"),
        "action_label":            rl_src.get("action_label"),
        "q_values":                rl_src.get("q_values"),
        "exploration_rate":        rl_src.get("exploration_rate"),
        "sessions_in_state_bucket": rl_src.get("sessions_in_state_bucket"),
    }

    # --- Voice direction (from affective recommendation) ---
    voice_src = _deep_get(aff_payload, "voice_direction") or _deep_get(aff_payload, "recommendation", "voice_direction") or {}
    voice_direction = {
        "tone":              voice_src.get("tone"),
        "pace":              voice_src.get("pace"),
        "register":          voice_src.get("register"),
        "pitch_variation":   voice_src.get("pitch_variation"),
        "suggested_opening": voice_src.get("suggested_opening"),
        "avoid":             voice_src.get("avoid", []),
    }

    # --- Ground truth (if DEAP data was used) ---
    ground_truth = data.get("eeg_data", {}).get("ground_truth")

    output = {
        "timestamp": now_ts,
        "session_id": data.get("session_id"),
        "participant_id": data.get("participant_id"),
        "release_gate": review_result.get("release_gate",
                        _deep_get(review_result, "payload", "release_gate")),
        "eeg_features": eeg_features,
        "vad": vad,
        "relational_states": relational_states,
        "nlp_emotion_map": nlp_emotion_map,
        "trajectory_interpretation": trajectory_interpretation,
        "specialist_notes": specialist_notes,
        "rl_agent": rl_agent,
        "voice_direction": voice_direction,
    }

    if ground_truth:
        output["ground_truth"] = ground_truth

    return output


def _save_voice_output(voice_output: dict) -> Path:
    """Save voice output JSON to the output directory and return the file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pid = voice_output.get("participant_id", "unknown")
    sid = voice_output.get("session_id", "")[:20]
    filename = f"voice_output_{pid}_{ts}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(voice_output, f, indent=2, default=str)

    return filepath


# ═══════════════════════════════════════════════════════════════
# MAIN AFFECTIVE COMPUTING PIPELINE
# ═══════════════════════════════════════════════════════════════

async def run_affective_pipeline(data: dict, ws):
    """
    Full pipeline: EEG data + context → agent chain → affective state → review.

    Expected data fields:
      - eeg_data: raw EEG features / signal summary
      - context_events: behavioral events, environment info
      - voice_text: voice/text sentiment data (optional)
      - session_id: session identifier
      - participant_id: participant identifier
    """
    session_id = data.get("session_id", str(uuid.uuid4()))
    participant_id = data.get("participant_id", "unknown")
    eeg_data = data.get("eeg_data", {})
    context_events = data.get("context_events", {})
    voice_text = data.get("voice_text", {})

    try:
        # ── Phase 1: EEG Agent — feature extraction ──────────────
        await send(ws, {
            "type": "phase",
            "phase": "EEG Analysis",
            "label": "EEG Agent analyzing signal…",
        })

        eeg_input = json.dumps({
            "session_id": session_id,
            "participant_id": participant_id,
            "eeg_data": eeg_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2)

        eeg_result = await run_agent(
            AGENTS["eeg"],
            f"Process this EEG data and emit EEGFeatureEvidenceV1:\n\n{eeg_input}",
            ws, session_id, participant_id,
        )

        # ── Phase 2: Context Agent — contamination & context ─────
        await send(ws, {
            "type": "phase",
            "phase": "Context Analysis",
            "label": "Context Agent assessing environment…",
        })

        context_input = json.dumps({
            "session_id": session_id,
            "participant_id": participant_id,
            "context_events": context_events,
            "voice_text": voice_text,
            "eeg_signal_quality": eeg_result.get("quality", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2)

        context_result = await run_agent(
            AGENTS["context"],
            f"Assess context and contamination, emit ContextContaminationStateV1:\n\n{context_input}",
            ws, session_id, participant_id,
        )

        # ── Phase 3: Affective Agent — emotional synthesis ────────
        await send(ws, {
            "type": "phase",
            "phase": "Affective Synthesis",
            "label": "Affective Agent synthesizing emotional state…",
        })

        affective_input = json.dumps({
            "session_id": session_id,
            "participant_id": participant_id,
            "eeg_evidence": eeg_result,
            "context_state": context_result,
            "voice_text": voice_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2)

        affective_result = await run_agent(
            AGENTS["affective"],
            f"Synthesize the emotional state from upstream evidence, emit AffectiveStateV1:\n\n{affective_input}",
            ws, session_id, participant_id,
        )

        # ── Phase 4: Master Neuroscientist — review & gating ─────
        await send(ws, {
            "type": "phase",
            "phase": "Neuroscience Review",
            "label": "Master Neuroscientist reviewing evidence chain…",
        })

        review_input = json.dumps({
            "session_id": session_id,
            "participant_id": participant_id,
            "eeg_evidence": eeg_result,
            "context_state": context_result,
            "affective_state": affective_result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2)

        review_result = await run_agent(
            AGENTS["master"],
            f"Review all upstream outputs for scientific validity, emit NeuroscienceReviewV1:\n\n{review_input}",
            ws, session_id, participant_id,
        )

        # ── Phase 5: Emit final result to downstream ─────────────
        final_output = {
            "type": "pipeline_result",
            "session_id": session_id,
            "participant_id": participant_id,
            "eeg_evidence": eeg_result,
            "context_state": context_result,
            "affective_state": affective_result,
            "neuroscience_review": review_result,
            "release_gate": review_result.get("release_gate", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await send(ws, final_output)
        log.info(f"Pipeline complete. release_gate={final_output['release_gate']}")

        # ── Always save voice output JSON (regardless of release gate) ──
        try:
            voice_output = _compose_voice_output(
                eeg_result, context_result, affective_result, review_result, data,
            )
            filepath = _save_voice_output(voice_output)
            log.info(f"Voice output saved: {filepath}")
            await send(ws, {
                "type": "voice_output_saved",
                "path": str(filepath),
                "voice_output": voice_output,
            })

            # Broadcast to voice app clients
            await _broadcast_voice_state(dict(voice_output))
        except Exception as save_err:
            log.error(f"Failed to save voice output: {save_err}")

    except Exception as e:
        log.error(f"Pipeline error: {traceback.format_exc()}")
        await send(ws, {"type": "error", "message": str(e)})


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET HANDLER
# ═══════════════════════════════════════════════════════════════

async def send(ws, data: dict):
    """Safe send helper."""
    try:
        await ws.send(json.dumps(data, default=str))
    except Exception as e:
        log.warning(f"Send failed: {e}")


async def handle_client(websocket):
    log.info(f"Client connected: {websocket.remote_address}")

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("Invalid JSON received")
                continue

            msg_type = msg.get("type")

            if msg_type == "eeg_data":
                # Full pipeline: EEG + context → affective state → review
                log.info("EEG data received, starting affective pipeline")
                asyncio.create_task(run_affective_pipeline(msg, websocket))

            elif msg_type == "ping":
                await send(websocket, {"type": "pong"})

            # ── Voice App Bridge Commands ──────────────────
            elif msg_type == "register_voice":
                _voice_clients.add(websocket)
                log.info(f"Voice app registered ({len(_voice_clients)} total)")
                # Send latest state immediately if available
                if _latest_voice_state:
                    await send(websocket, _latest_voice_state)

            elif msg_type == "set_sim_state":
                # Demo injection from voice app (calm/anxious/engaged buttons)
                state_name = msg.get("name", "")
                if state_name in _SIM_STATES:
                    sim_state = dict(_SIM_STATES[state_name])
                    log.info(f"Voice sim state injected: {state_name}")
                    await _broadcast_voice_state(sim_state)
                else:
                    await send(websocket, {"type": "error",
                                           "message": f"Unknown sim state: {state_name}"})

            elif msg_type == "inject_state":
                # Direct state injection from voice app
                injected = msg.get("state")
                if injected and isinstance(injected, dict):
                    log.info("Voice state injected directly")
                    await _broadcast_voice_state(injected)

            elif msg_type == "get_agents":
                # Return agent registry for frontend display
                agents_info = [
                    {
                        "id": a.id,
                        "name": a.name,
                        "role": a.role,
                        "canonical_output": a.canonical_output,
                    }
                    for a in AGENTS.values()
                ]
                await send(websocket, {"type": "agents", "agents": agents_info})

            # ── DEAP Simulator Commands ─────────────────────────
            elif msg_type == "deap_list":
                try:
                    loader = DEAPLoader(str(DEAP_DATA_DIR))
                    participants = loader.list_participants()
                    await send(websocket, {
                        "type": "deap_participants",
                        "participants": participants,
                        "trials_per_participant": 40,
                        "channels": DEAP_CHANNEL_MAPPING,
                    })
                except Exception as e:
                    await send(websocket, {"type": "error",
                                           "message": f"DEAP data not found: {e}"})

            elif msg_type == "deap_start":
                participant = msg.get("participant_id", "s01")
                trial = msg.get("trial_id", 0)
                rate = msg.get("playback_rate", 2.0)
                session_id = msg.get("session_id", f"deap-{participant}-{trial}-{uuid.uuid4().hex[:6]}")

                # Stop any running simulator for this client
                ws_id = id(websocket)
                if ws_id in _client_simulators:
                    old = _client_simulators[ws_id]
                    if old.get("task"):
                        old["task"].cancel()
                    try:
                        old["simulator"].stop()
                    except Exception:
                        pass

                try:
                    sim = DEAPSimulator(
                        data_directory=str(DEAP_DATA_DIR),
                        window_size_seconds=4.0,
                        step_size_seconds=1.0,
                    )
                    sim.load_trial(participant, trial)
                    sim.set_playback_rate(rate)

                    task = asyncio.create_task(
                        _run_deap_stream(sim, websocket, session_id))
                    _client_simulators[ws_id] = {
                        "simulator": sim,
                        "task": task,
                        "session_id": session_id,
                        "last_features": None,
                    }
                    log.info(f"DEAP started: {participant} trial {trial} @ {rate}x")

                except Exception as e:
                    log.error(f"DEAP start error: {e}")
                    await send(websocket, {"type": "error",
                                           "message": f"DEAP start failed: {e}"})

            elif msg_type == "deap_stop":
                ws_id = id(websocket)
                if ws_id in _client_simulators:
                    state = _client_simulators.pop(ws_id)
                    if state.get("task"):
                        state["task"].cancel()
                    try:
                        state["simulator"].stop()
                    except Exception:
                        pass
                    await send(websocket, {"type": "deap_status", "status": "stopped"})

            elif msg_type == "deap_pause":
                ws_id = id(websocket)
                state = _client_simulators.get(ws_id)
                if state:
                    try:
                        state["simulator"].pause()
                        await send(websocket, {"type": "deap_status", "status": "paused"})
                    except Exception as e:
                        await send(websocket, {"type": "error", "message": str(e)})

            elif msg_type == "deap_resume":
                ws_id = id(websocket)
                state = _client_simulators.get(ws_id)
                if state:
                    try:
                        state["simulator"].resume()
                        await send(websocket, {"type": "deap_status", "status": "playing"})
                    except Exception as e:
                        await send(websocket, {"type": "error", "message": str(e)})

            elif msg_type == "deap_analyze":
                # Run full agent pipeline on current DEAP features
                ws_id = id(websocket)
                state = _client_simulators.get(ws_id)
                last = state.get("last_features") if state else None
                if not last:
                    await send(websocket, {"type": "error",
                                           "message": "No DEAP data to analyze. Start simulation first."})
                else:
                    # Build pipeline input from extracted features
                    pipeline_data = {
                        "session_id": state.get("session_id", ""),
                        "participant_id": last["metadata"]["participant_id"],
                        "eeg_data": {
                            "features": last["features"],
                            "band_powers": last["band_powers"],
                            "window": {
                                "start_time": last["start_time"],
                                "end_time": last["end_time"],
                                "index": last["window_index"],
                            },
                            "channels": last["channels"],
                            "sampling_rate": last["sampling_rate"],
                            "ground_truth": last["metadata"],
                        },
                        "context_events": msg.get("context_events", {
                            "source": "DEAP_dataset",
                            "phase": "video_watching",
                            "ground_truth_available": True,
                        }),
                        "voice_text": msg.get("voice_text", {}),
                    }
                    log.info(f"Running agent pipeline on DEAP window {last['window_index']}")
                    asyncio.create_task(run_affective_pipeline(pipeline_data, websocket))

            # ── Live Muse EEG Commands ──────────────────────
            elif msg_type == "muse_start":
                session_id = msg.get("session_id", f"muse-{uuid.uuid4().hex[:8]}")
                auto_analyze = msg.get("auto_analyze", True)
                analyze_interval = max(10, msg.get("analyze_interval", 15))

                # Stop any existing Muse stream for this client
                ws_id = id(websocket)
                if ws_id in _client_muse:
                    old = _client_muse[ws_id]
                    old["running"] = False
                    if old.get("task"):
                        old["task"].cancel()

                task = asyncio.create_task(_run_muse_stream(websocket, session_id))
                _client_muse[ws_id] = {
                    "task": task,
                    "running": True,
                    "session_id": session_id,
                    "last_features": None,
                    "auto_analyze": auto_analyze,
                    "analyze_interval": analyze_interval,
                    "last_analyze_time": 0,
                    "pipeline_task": None,
                }
                log.info(f"Muse live stream requested: {session_id} "
                         f"(auto_analyze={auto_analyze}, interval={analyze_interval}s)")

            elif msg_type == "muse_stop":
                ws_id = id(websocket)
                if ws_id in _client_muse:
                    state = _client_muse.pop(ws_id)
                    state["running"] = False
                    if state.get("task"):
                        state["task"].cancel()
                    await send(websocket, {"type": "muse_status", "status": "stopped"})

            elif msg_type == "muse_analyze":
                ws_id = id(websocket)
                state = _client_muse.get(ws_id)
                last = state.get("last_features") if state else None
                if not last:
                    await send(websocket, {"type": "error",
                                           "message": "No live EEG data. Start Muse stream first."})
                else:
                    pipeline_data = {
                        "session_id": state.get("session_id", ""),
                        "participant_id": "live_muse",
                        "eeg_data": {
                            "features": last["features"],
                            "band_powers": last["band_powers"],
                            "window": {
                                "start_time": last["start_time"],
                                "end_time": last["end_time"],
                                "index": last["window_index"],
                            },
                            "channels": last["channels"],
                            "sampling_rate": last["sampling_rate"],
                        },
                        "context_events": msg.get("context_events", {
                            "source": "live_muse_eeg",
                            "phase": "live_recording",
                            "device": "Muse",
                        }),
                        "voice_text": msg.get("voice_text", {}),
                    }
                    log.info(f"Running agent pipeline on live Muse window {last['window_index']}")
                    asyncio.create_task(run_affective_pipeline(pipeline_data, websocket))

            else:
                log.warning(f"Unknown message type: {msg_type}")
                await send(websocket, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except websockets.exceptions.ConnectionClosed:
        log.info("Client disconnected")
    except Exception as e:
        log.error(f"Client handler error: {traceback.format_exc()}")
    finally:
        # Clean up DEAP simulator on disconnect
        ws_id = id(websocket)
        if ws_id in _client_simulators:
            state = _client_simulators.pop(ws_id)
            if state.get("task"):
                state["task"].cancel()
            try:
                state["simulator"].stop()
            except Exception:
                pass
        # Clean up Muse stream on disconnect
        if ws_id in _client_muse:
            state = _client_muse.pop(ws_id)
            state["running"] = False
            if state.get("task"):
                state["task"].cancel()
        # Clean up voice client registration
        _voice_clients.discard(websocket)


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

async def main():
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Export it: export ANTHROPIC_API_KEY=your-key"
        )

    # Check DEAP data availability
    deap_available = DEAP_DATA_DIR.exists()
    deap_count = len(list(DEAP_DATA_DIR.glob("s*.dat"))) if deap_available else 0

    log.info(f"🧠 Empathetic Robot Framework starting on ws://{WS_HOST}:{WS_PORT}")
    log.info(f"   Model: {MODEL}")
    log.info(f"   Agents: {', '.join(a.name for a in AGENTS.values())}")
    log.info(f"   DEAP data: {deap_count} participants in {DEAP_DATA_DIR}" if deap_available
             else "   DEAP data: NOT FOUND")
    log.info(f"   Live Muse EEG: {'AVAILABLE (pylsl installed)' if LSL_AVAILABLE else 'NOT AVAILABLE (pip install pylsl)'}")
    log.info(f"   Voice bridge: ENABLED (voice apps send {{type:'register_voice'}} to receive EEG state)")

    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        log.info("Affective computing server is listening.")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())

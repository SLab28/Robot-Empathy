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
        # Clean up simulator on disconnect
        ws_id = id(websocket)
        if ws_id in _client_simulators:
            state = _client_simulators.pop(ws_id)
            if state.get("task"):
                state["task"].cancel()
            try:
                state["simulator"].stop()
            except Exception:
                pass


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

    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        log.info("Affective computing server is listening.")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())

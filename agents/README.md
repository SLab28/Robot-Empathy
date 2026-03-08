# Empathetic Robot Framework — Agent Server

Real-time affective computing system that enables robots to adapt to individual users' emotional states by analyzing EEG data through specialized AI agents.

## Architecture

Four specialized Claude agents coordinated by a master agent:

1. **EEG Agent** — Signal processing & feature extraction → `EEGFeatureEvidenceV1`
2. **Context Agent** — Behavioral & environmental monitoring → `ContextContaminationStateV1`
3. **Affective Agent** — Emotional state synthesis → `AffectiveStateV1`
4. **Master Neuroscientist** — Output auditing & gating → `NeuroscienceReviewV1`

```
Raw EEG + Events
       │
       ▼
  EEG Agent ──────────────┐
       │                  │
       ▼                  │
  Context Agent           │
       │                  │
       ▼                  ▼
  Affective Agent ← (both inputs)
       │
       ▼
  Master Neuroscientist
       │
       ▼
  Downstream (Robot / RL / WebXR)
```

## Agent Definition Files

Each agent loads its knowledge from paired SKILL + RULES markdown files:

| File | Purpose |
|---|---|
| `00_system_orchestration_RULES.md` | Shared governance, routing graph, core laws |
| `01_eeg_agent_SKILL.md` | EEG domain knowledge, preprocessing, features |
| `02_eeg_agent_RULES.md` | EEGFeatureEvidenceV1 contract |
| `03_affective_agent_SKILL.md` | Emotion theory, VAD, relational states |
| `04_affective_agent_RULES.md` | AffectiveStateV1 contract |
| `05_context_agent_SKILL.md` | Contamination, clinical protocol, sentiment |
| `06_context_agent_RULES.md` | ContextContaminationStateV1 contract |
| `07_master_neuroscientist_SKILL.md` | Review, governance, failure modes |
| `08_master_neuroscientist_RULES.md` | NeuroscienceReviewV1 contract |

## Setup

```bash
conda activate hidden
cd path/to/agents
pip install -r requirements.txt
```

Set your API key:
```bash
export ANTHROPIC_API_KEY=your-key
```

## Run

```bash
python server.py
```

You should see:
```
🧠 Empathetic Robot Framework starting on ws://localhost:8765
   Model: claude-sonnet-4-6
   Agents: EEG Signal Analysis Specialist, Context, Clinical & Contamination Agent, Affective Computing Specialist, Master Neuroscientist Orchestrator
Affective computing server is listening.
```
Usage:
---
Server starting on ws://localhost:8765
Spirit server is listening. Open frontend/index.html in your browser.
To stop the server, press Ctrl+C in the terminal.
```
conda activate hidden
cd path\to\agents
python -m http.server 3000
```
Then open your browser and go to:
```
http://localhost:3000
To stop the server, press Ctrl+C in the terminal.
```
## Test run
-> input: now I'm teling you a story.
Agents discuss and give the output:
A lone figure stands at the edge of a dimly lit stage, one arm extended toward the audience with open cupped hands while the torso leans gently back, weight shifting forward on trembling feet — soft golden light pools at their feet like a threshold, the surrounding darkness breathing with deep indigo and warm amber, as a single slow exhale of visible breath rises from parted lips into the stillness, carrying the whole unspoken world of a story not yet born.
API usage: (not the SDK yet)
Tokens in:2038
Tokens out: 723
Tokens total: 2761
Cost: 0.02 usd
# State log
-> no agents sdk
-> no stream diffusion
-> no wbXR integration
But it is kinda cool 
---

## WebSocket Protocol

### Send EEG data to start the pipeline:
```json
{
  "type": "eeg_data",
  "session_id": "session-001",
  "participant_id": "participant-001",
  "eeg_data": { ... },
  "context_events": { ... },
  "voice_text": { ... }
}
```

### Receive streaming agent outputs:
- `agent_thinking` — agent started processing
- `agent_speaking` — streaming text from agent
- `agent_done` — agent finished
- `phase` — pipeline phase change
- `pipeline_result` — final combined output with `release_gate`

### Query agent registry:
```json
{ "type": "get_agents" }
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key |
| `EMPATHY_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `WS_HOST` | `localhost` | WebSocket host |
| `WS_PORT` | `8765` | WebSocket port |

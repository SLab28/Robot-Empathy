// voice-config.example.js — Template for voice-config.js
// Copy this file to voice-config.js and fill in your credentials.
// voice-config.js is gitignored (contains API keys).

export const VOICE_CONFIG = {
  // ElevenLabs API key (from elevenlabs.io dashboard)
  apiKey: 'your_elevenlabs_api_key_here',

  // EEG bridge WebSocket URL (agents/server.py)
  eegWsUrl: 'ws://localhost:8765',

  // Personas — each maps to an ElevenLabs agent
  personas: {
    tutor: {
      id: 'tutor',
      label: 'Learning Tutor',
      agentId: 'your_tutor_agent_id',
      voiceId: 'your_tutor_voice_id',
      hint: 'Calm, encouraging learning tutor. Adapts pacing based on cognitive state.',
      color: '#4A90D9',
    },
    workplace: {
      id: 'workplace',
      label: 'Workplace Coach',
      agentId: 'your_workplace_agent_id',
      voiceId: 'your_workplace_voice_id',
      hint: 'Professional onboarding coach. Adjusts complexity based on engagement.',
      color: '#27AE60',
    },
    clinical: {
      id: 'clinical',
      label: 'Clinical Companion',
      agentId: 'your_clinical_agent_id',
      voiceId: 'your_clinical_voice_id',
      hint: 'Warm, empathetic clinical companion. Prioritises comfort and safety.',
      color: '#8E44AD',
    },
  },
};

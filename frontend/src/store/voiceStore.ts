import { create } from 'zustand';

export type VoiceState = 'idle' | 'listening' | 'transcribing' | 'speaking' | 'acknowledged';

export interface VoiceOption {
  name: string;
  lang: string;
  isFemale: boolean;
  label: string;
}

interface VoiceStore {
  voiceState: VoiceState;
  audioAmplitude: number[];
  vramUsageMB: number;
  vramTotalMB: number;
  isMicActive: boolean;
  lastSpokenText: string;
  selectedVoiceName: string;
  speechRate: number;
  speechPitch: number;
  isAutoSpeakChat: boolean;      // Default FALSE: Only speak typed chat if user explicitly enables it!
  wakeWordEnabled: boolean;      // Hands-free "Hey Aura" continuous wake-word listening
  wakeWordStatus: 'idle' | 'standby' | 'detected' | 'capturing';
  wakeWordMessage: string;
  availableVoices: VoiceOption[];

  setVoiceState: (state: VoiceState) => void;
  setAudioAmplitude: (amp: number[]) => void;
  setVRAMTelemetry: (used: number, total: number) => void;
  setMicActive: (active: boolean) => void;
  setLastSpokenText: (text: string) => void;
  setSelectedVoiceName: (name: string) => void;
  setSpeechRate: (rate: number) => void;
  setSpeechPitch: (pitch: number) => void;
  setIsAutoSpeakChat: (auto: boolean) => void;
  setWakeWordEnabled: (enabled: boolean) => void;
  setWakeWordStatus: (status: 'idle' | 'standby' | 'detected' | 'capturing', msg?: string) => void;
  initVoices: () => void;
  speakText: (text: string, onEnd?: () => void) => void;
  playWakeAcknowledgement: (onDone?: () => void) => void;
}

// Preferred order of pleasant female voices on Windows
const PREFERRED_FEMALE_VOICES = [
  'Heera', 'Zira', 'Aria', 'Jenny', 'Sonia', 'Libby', 'Neerja', 'Natural', 'Female'
];

export const useVoiceStore = create<VoiceStore>((set, get) => ({
  voiceState: 'idle',
  audioAmplitude: [15, 30, 45, 25, 60, 40, 20],
  vramUsageMB: 22400,
  vramTotalMB: 24576,
  isMicActive: false,
  lastSpokenText: '',
  selectedVoiceName: 'Microsoft Heera - English (India)',
  speechRate: 1.0,
  speechPitch: 1.08,             // Warm feminine pitch
  isAutoSpeakChat: false,        // Requirement: NO voice back in chat unless enabled!
  wakeWordEnabled: true,         // Hands-free "Hey Aura" enabled by default
  wakeWordStatus: 'standby',
  wakeWordMessage: 'Listening for "Hey Aura"...',
  availableVoices: [],

  setVoiceState: (voiceState) => set({ voiceState }),
  setAudioAmplitude: (audioAmplitude) => set({ audioAmplitude }),
  setVRAMTelemetry: (vramUsageMB, vramTotalMB) => set({ vramUsageMB, vramTotalMB }),
  setMicActive: (isMicActive) => set({ isMicActive }),
  setLastSpokenText: (lastSpokenText) => set({ lastSpokenText }),
  setSelectedVoiceName: (selectedVoiceName) => set({ selectedVoiceName }),
  setSpeechRate: (speechRate) => set({ speechRate }),
  setSpeechPitch: (speechPitch) => set({ speechPitch }),
  setIsAutoSpeakChat: (isAutoSpeakChat) => set({ isAutoSpeakChat }),
  setWakeWordEnabled: (wakeWordEnabled) => set({ wakeWordEnabled }),
  setWakeWordStatus: (wakeWordStatus, msg) => set({
    wakeWordStatus,
    wakeWordMessage: msg || (
      wakeWordStatus === 'detected'
        ? '⚡ "Hey Aura" detected! Acknowledging...'
        : wakeWordStatus === 'capturing'
        ? '🎙️ Listening to your command...'
        : 'Listening for "Hey Aura"...'
    )
  }),

  initVoices: () => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;

    const load = () => {
      const raw = window.speechSynthesis.getVoices();
      if (!raw || raw.length === 0) return;

      const mapped: VoiceOption[] = raw.map((v) => {
        const lower = v.name.toLowerCase();
        const isFemale =
          lower.includes('zira') ||
          lower.includes('heera') ||
          lower.includes('aria') ||
          lower.includes('jenny') ||
          lower.includes('female') ||
          lower.includes('sonia') ||
          lower.includes('libby') ||
          lower.includes('neerja');

        let displayLabel = v.name.replace('Microsoft ', '').replace('Online (Natural) - ', '');
        if (isFemale) displayLabel += ' (Female)';

        return {
          name: v.name,
          lang: v.lang,
          isFemale,
          label: displayLabel
        };
      });

      // Filter to prioritize pleasant female voices (Heera / Zira)
      const femaleVoices = mapped.filter((v) => v.isFemale);
      let bestVoice = femaleVoices.find((v) =>
        PREFERRED_FEMALE_VOICES.some((pref) => v.name.includes(pref))
      );

      if (!bestVoice && femaleVoices.length > 0) {
        bestVoice = femaleVoices[0];
      }

      set({
        availableVoices: mapped,
        selectedVoiceName: bestVoice ? bestVoice.name : get().selectedVoiceName
      });
    };

    load();
    window.speechSynthesis.onvoiceschanged = load;
  },

  speakText: (text: string, onEnd?: () => void) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      onEnd?.();
      return;
    }
    window.speechSynthesis.cancel();
    set({ voiceState: 'speaking' });

    // Clean markdown and code formatting for pleasant natural speech
    const cleanSpeech = text
      .replace(/```[\s\S]*?```/g, 'Code block omitted.')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/[*#_~]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .trim();

    if (!cleanSpeech) {
      set({ voiceState: 'idle' });
      onEnd?.();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(cleanSpeech);
    const voices = window.speechSynthesis.getVoices();
    const { selectedVoiceName, speechRate, speechPitch } = get();

    const voice = voices.find(v => v.name === selectedVoiceName) ||
                  voices.find(v => v.name.toLowerCase().includes('heera')) ||
                  voices.find(v => v.name.toLowerCase().includes('zira')) ||
                  voices.find(v => v.name.toLowerCase().includes('female'));

    if (voice) utterance.voice = voice;
    utterance.rate = speechRate || 1.0;
    utterance.pitch = speechPitch || 1.08;

    utterance.onend = () => {
      set({ voiceState: 'idle' });
      onEnd?.();
    };
    utterance.onerror = () => {
      set({ voiceState: 'idle' });
      onEnd?.();
    };

    window.speechSynthesis.speak(utterance);
  },

  playWakeAcknowledgement: (onDone?: () => void) => {
    // Immediate pleasant female voice acknowledgment
    const { speakText } = get();
    set({ voiceState: 'acknowledged', wakeWordStatus: 'detected' });
    speakText("I'm listening.", () => {
      set({ voiceState: 'listening', wakeWordStatus: 'capturing' });
      onDone?.();
    });
  }
}));

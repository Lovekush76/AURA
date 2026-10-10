import { create } from 'zustand';

export type AuraModelId =
  | 'auto'
  | 'nvidia/nemotron-3-ultra'
  | 'qwen2.5:0.5b'
  | 'qwen3.5:4b'
  | 'deepseek-r1:14b';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'aura';
  text: string;
  timestamp: string;
  modelUsed?: string;
  tps?: number;
}

interface ChatStore {
  messages: ChatMessage[];
  isStreaming: boolean;
  selectedModel: AuraModelId;
  liveTps: number;
  peakTps: number;
  contextWindowLabel: string;
  addMessage: (sender: 'user' | 'aura', text: string, modelUsed?: string, tps?: number) => void;
  appendStreamChunk: (chunk: string, currentTps?: number) => void;
  setStreaming: (streaming: boolean) => void;
  setSelectedModel: (model: AuraModelId) => void;
  setLiveTps: (tps: number) => void;
  clearChat: () => void;
}

export const MODEL_CATALOG: Record<
  AuraModelId,
  { label: string; short: string; context: string; badgeColor: string; desc: string }
> = {
  auto: {
    label: 'Aura Smart Router (Auto)',
    short: 'Smart Router',
    context: '1M / 128K Dynamic',
    badgeColor: 'cyan',
    desc: 'Semantic Fast-Path (385 TPS) + Hybrid RRF + Dynamic Tier Routing'
  },
  'nvidia/nemotron-3-ultra': {
    label: 'NVIDIA Nemotron 3 Ultra (550B)',
    short: 'Nemotron 3 Ultra',
    context: '1,000,000 Tokens',
    badgeColor: 'emerald',
    desc: '1M-token Mamba-2 Hybrid Transformer for repository-wide deep reasoning'
  },
  'qwen2.5:0.5b': {
    label: 'Qwen 2.5 Turbo (0.5B Local)',
    short: 'Qwen 2.5 Turbo',
    context: '32,768 Tokens',
    badgeColor: 'cyan',
    desc: 'Ultra-low latency local FlashAttention generation (150–385 TPS)'
  },
  'qwen3.5:4b': {
    label: 'Qwen 3.5 Voice Core (4B Local)',
    short: 'Qwen 3.5 4B',
    context: '131,072 Tokens',
    badgeColor: 'purple',
    desc: 'Balanced conversational & voice synthesis core with 128K context'
  },
  'deepseek-r1:14b': {
    label: 'DeepSeek R1 Reasoning (14B)',
    short: 'DeepSeek R1 14B',
    context: '131,072 Tokens',
    badgeColor: 'amber',
    desc: 'Chain-of-thought mathematical, algorithmic & multi-file code solver'
  }
};

export const useChatStore = create<ChatStore>((set) => ({
  messages: [
    {
      id: 'init-1',
      sender: 'aura',
      text: 'Aura v3.5 Holographic Core online. Hybrid RRF Context Engine (1M-token Nemotron 3 Ultra + 10M Episodic Vault) & FlashAttention Turbo (257–385 TPS) active.',
      timestamp: new Date().toLocaleTimeString(),
      modelUsed: 'Aura Smart Router',
      tps: 362.5
    }
  ],
  isStreaming: false,
  selectedModel: 'auto',
  liveTps: 362.5,
  peakTps: 385.2,
  contextWindowLabel: '1M / 10M Episodic',
  addMessage: (sender, text, modelUsed, tps) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: Math.random().toString(36).substring(7),
          sender,
          text,
          timestamp: new Date().toLocaleTimeString(),
          modelUsed,
          tps
        }
      ]
    })),
  appendStreamChunk: (chunk, currentTps) =>
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      const activeModelLabel = MODEL_CATALOG[state.selectedModel]?.short || 'Aura Core';
      const updatedTps = currentTps && currentTps > 0 ? currentTps : state.liveTps;
      const newPeak = Math.max(state.peakTps, updatedTps);

      if (last && last.sender === 'aura') {
        last.text += chunk;
        last.modelUsed = activeModelLabel;
        last.tps = updatedTps;
        return { messages: msgs, liveTps: updatedTps, peakTps: newPeak };
      } else {
        return {
          liveTps: updatedTps,
          peakTps: newPeak,
          messages: [
            ...msgs,
            {
              id: Math.random().toString(36).substring(7),
              sender: 'aura',
              text: chunk,
              timestamp: new Date().toLocaleTimeString(),
              modelUsed: activeModelLabel,
              tps: updatedTps
            }
          ]
        };
      }
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setSelectedModel: (selectedModel) =>
    set({
      selectedModel,
      contextWindowLabel: MODEL_CATALOG[selectedModel]?.context || '1M Dynamic'
    }),
  setLiveTps: (liveTps) =>
    set((s) => ({
      liveTps,
      peakTps: Math.max(s.peakTps, liveTps)
    })),
  clearChat: () => set({ messages: [] })
}));

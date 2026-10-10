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
  activeRoutedModel: string | null;
  liveTps: number;
  peakTps: number;
  contextWindowLabel: string;
  addMessage: (sender: 'user' | 'aura', text: string, modelUsed?: string, tps?: number) => void;
  appendStreamChunk: (chunk: string, currentTps?: number, routedModel?: string) => void;
  setActiveRoutedModel: (model: string | null) => void;
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
    context: '2,048 Tokens',
    badgeColor: 'cyan',
    desc: 'Ultra-low latency local FlashAttention generation (150–385 TPS)'
  },
  'qwen3.5:4b': {
    label: 'Qwen 3.5 Voice Core (4B Local)',
    short: 'Qwen 3.5 4B',
    context: '4,096 / 1,536 Voice',
    badgeColor: 'purple',
    desc: 'Balanced conversational & voice synthesis core'
  },
  'deepseek-r1:14b': {
    label: 'DeepSeek R1 Reasoning (14B)',
    short: 'DeepSeek R1 14B',
    context: '32,768 Tokens',
    badgeColor: 'amber',
    desc: 'Chain-of-thought mathematical, algorithmic & multi-file code solver'
  }
};

export function formatModelBadge(modelId?: string | null, fallbackSelect?: AuraModelId): string {
  if (modelId && modelId in MODEL_CATALOG) {
    return MODEL_CATALOG[modelId as AuraModelId].short;
  }
  if (modelId && modelId.trim()) {
    return modelId;
  }
  if (fallbackSelect && fallbackSelect in MODEL_CATALOG) {
    return MODEL_CATALOG[fallbackSelect].short;
  }
  return 'Aura Core';
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [
    {
      id: 'init-1',
      sender: 'aura',
      text: 'Aura v3.5 Holographic Core online. Hybrid RRF Context Engine & FlashAttention Turbo active.',
      timestamp: new Date().toLocaleTimeString(),
      modelUsed: 'Aura Smart Router',
      tps: 362.5
    }
  ],
  isStreaming: false,
  selectedModel: 'auto',
  activeRoutedModel: null,
  liveTps: 362.5,
  peakTps: 385.2,
  contextWindowLabel: '1M / 10M Episodic',
  addMessage: (sender, text, modelUsed, tps) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: Math.random().toString(36).substring(2, 9),
          sender,
          text,
          timestamp: new Date().toLocaleTimeString(),
          modelUsed,
          tps
        }
      ]
    })),
  setActiveRoutedModel: (activeRoutedModel) => set({ activeRoutedModel }),
  appendStreamChunk: (chunk, currentTps, routedModel) =>
    set((state) => {
      const updatedTps = currentTps && currentTps > 0 ? currentTps : state.liveTps;
      const newPeak = Math.max(state.peakTps, updatedTps);
      const effectiveRouted = routedModel || state.activeRoutedModel;
      const resolvedModelLabel = formatModelBadge(effectiveRouted, state.selectedModel);

      const lastIdx = state.messages.length - 1;
      const last = lastIdx >= 0 ? state.messages[lastIdx] : undefined;

      if (last && last.sender === 'aura') {
        const updatedMessage: ChatMessage = {
          ...last,
          text: last.text + chunk,
          modelUsed: resolvedModelLabel,
          tps: updatedTps
        };
        const nextMessages = state.messages.slice(0, lastIdx);
        nextMessages.push(updatedMessage);
        return {
          messages: nextMessages,
          activeRoutedModel: effectiveRouted || state.activeRoutedModel,
          liveTps: updatedTps,
          peakTps: newPeak
        };
      }

      const newMessage: ChatMessage = {
        id: Math.random().toString(36).substring(2, 9),
        sender: 'aura',
        text: chunk,
        timestamp: new Date().toLocaleTimeString(),
        modelUsed: resolvedModelLabel,
        tps: updatedTps
      };

      return {
        liveTps: updatedTps,
        peakTps: newPeak,
        activeRoutedModel: effectiveRouted || state.activeRoutedModel,
        messages: [...state.messages, newMessage]
      };
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
  clearChat: () => set({ messages: [], activeRoutedModel: null })
}));

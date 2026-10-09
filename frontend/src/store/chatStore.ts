import { create } from 'zustand';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'aura';
  text: string;
  timestamp: string;
}

interface ChatStore {
  messages: ChatMessage[];
  isStreaming: boolean;
  addMessage: (sender: 'user' | 'aura', text: string) => void;
  appendStreamChunk: (chunk: string) => void;
  setStreaming: (streaming: boolean) => void;
  clearChat: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [
    {
      id: 'init-1',
      sender: 'aura',
      text: 'Standing by. Voice core mapped to qwen3.5:4b.',
      timestamp: new Date().toLocaleTimeString()
    }
  ],
  isStreaming: false,
  addMessage: (sender, text) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: Math.random().toString(36).substring(7),
          sender,
          text,
          timestamp: new Date().toLocaleTimeString()
        }
      ]
    })),
  appendStreamChunk: (chunk) =>
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.sender === 'aura') {
        last.text += chunk;
        return { messages: msgs };
      } else {
        return {
          messages: [
            ...msgs,
            {
              id: Math.random().toString(36).substring(7),
              sender: 'aura',
              text: chunk,
              timestamp: new Date().toLocaleTimeString()
            }
          ]
        };
      }
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  clearChat: () => set({ messages: [] })
}));

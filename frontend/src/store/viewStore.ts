import { create } from 'zustand';

export type ActiveTab = 'chat' | 'workspace' | 'voice' | 'profile';

interface ViewStore {
  activeTab: ActiveTab;
  isSplitView: boolean;
  setActiveTab: (tab: ActiveTab) => void;
  toggleSplitView: () => void;
  setSplitView: (split: boolean) => void;
}

export const useViewStore = create<ViewStore>((set) => ({
  activeTab: 'chat',
  isSplitView: false,
  setActiveTab: (activeTab) => set({ activeTab }),
  toggleSplitView: () => set((s) => ({ isSplitView: !s.isSplitView })),
  setSplitView: (isSplitView) => set({ isSplitView })
}));

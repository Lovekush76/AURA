import { create } from 'zustand';

export type ActiveTab = 'chat' | 'workspace' | 'voice' | 'profile' | 'core3d';

interface ViewStore {
  activeTab: ActiveTab;
  isSplitView: boolean;
  show3DCoreDock: boolean;
  is3DTiltEnabled: boolean;
  setActiveTab: (tab: ActiveTab) => void;
  toggleSplitView: () => void;
  setSplitView: (split: boolean) => void;
  toggle3DCoreDock: () => void;
  toggle3DTilt: () => void;
}

export const useViewStore = create<ViewStore>((set) => ({
  activeTab: 'chat',
  isSplitView: false,
  show3DCoreDock: true,
  is3DTiltEnabled: true,
  setActiveTab: (activeTab) => set({ activeTab }),
  toggleSplitView: () => set((s) => ({ isSplitView: !s.isSplitView })),
  setSplitView: (isSplitView) => set({ isSplitView }),
  toggle3DCoreDock: () => set((s) => ({ show3DCoreDock: !s.show3DCoreDock })),
  toggle3DTilt: () => set((s) => ({ is3DTiltEnabled: !s.is3DTiltEnabled }))
}));

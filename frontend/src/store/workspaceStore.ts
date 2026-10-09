import { create } from 'zustand';

interface WorkspaceStore {
  activeFilePath: string;
  activeFileContent: string;
  proposedDiff: string | null;
  fileTree: Array<{ path: string; is_dir: boolean; size: number }>;
  setActiveFile: (path: string, content: string) => void;
  setProposedDiff: (diff: string | null) => void;
  setFileTree: (tree: Array<{ path: string; is_dir: boolean; size: number }>) => void;
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  activeFilePath: 'src/server/auth.py',
  activeFileContent: '# aura. Developer Workspace\n# Ready.\n\ndef authenticate():\n    return True\n',
  proposedDiff: null,
  fileTree: [],
  setActiveFile: (path, content) => set({ activeFilePath: path, activeFileContent: content }),
  setProposedDiff: (diff) => set({ proposedDiff: diff }),
  setFileTree: (tree) => set({ fileTree: tree })
}));

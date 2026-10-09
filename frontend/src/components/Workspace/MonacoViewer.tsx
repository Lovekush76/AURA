import MonacoEditor from '@monaco-editor/react';
import { useWorkspaceStore } from '../../store/workspaceStore';

export const MonacoViewer = () => {
  const { activeFileContent, setActiveFile, activeFilePath } = useWorkspaceStore();

  return (
    <div className="flex-1 w-full h-full">
      <MonacoEditor
        height="100%"
        language={activeFilePath.endsWith('.py') ? 'python' : activeFilePath.endsWith('.ts') || activeFilePath.endsWith('.tsx') ? 'typescript' : 'plaintext'}
        theme="vs-dark"
        value={activeFileContent}
        onChange={(val) => setActiveFile(activeFilePath, val || '')}
        options={{
          readOnly: false,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: 'monospace',
          scrollBeyondLastLine: false,
          automaticLayout: true
        }}
      />
    </div>
  );
};

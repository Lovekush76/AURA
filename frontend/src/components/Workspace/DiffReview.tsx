import { useState } from 'react';
import { Code, Check, X, RefreshCw } from 'lucide-react';
import { useWorkspaceStore } from '../../store/workspaceStore';

export const DiffReview = () => {
  const { activeFilePath, proposedDiff, setProposedDiff } = useWorkspaceStore();
  const [isApplying, setIsApplying] = useState(false);

  const handleApply = async () => {
    if (!proposedDiff) return;
    setIsApplying(true);
    try {
      const resp = await fetch('/api/v1/workspace/patch', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer aura_sec_default_change_me'
        },
        body: JSON.stringify({ diff: proposedDiff })
      });
      const data = await resp.json();
      if (data.ok) {
        alert('Patch successfully verified and committed to Git checkpoint!');
        setProposedDiff(null);
      } else {
        alert(`Failed: ${data.detail || data.error}`);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(`Error applying patch: ${msg}`);
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div className="flex justify-between items-center bg-black/40 border-b border-white/[0.08] px-4 py-3">
      <div className="flex items-center gap-2 text-xs">
        <Code className="text-cyan-400" size={14} />
        <span className="text-white font-semibold">{activeFilePath}</span>
        <span className="text-white/40">(live workspace)</span>
      </div>

      {proposedDiff && (
        <div className="flex gap-2">
          <button
            onClick={handleApply}
            disabled={isApplying}
            className="flex items-center gap-1 text-xs px-2.5 py-1 bg-green-500/20 text-green-400 border border-green-500/30 rounded-md hover:bg-green-500/30 transition-colors"
          >
            {isApplying ? <RefreshCw className="animate-spin" size={12} /> : <Check size={12} />}
            Apply Patch
          </button>
          <button
            onClick={() => setProposedDiff(null)}
            className="flex items-center gap-1 text-xs px-2.5 py-1 bg-red-500/20 text-red-400 border border-red-500/30 rounded-md hover:bg-red-500/30 transition-colors"
          >
            <X size={12} /> Reject
          </button>
        </div>
      )}
    </div>
  );
};

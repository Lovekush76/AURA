import { useEffect } from 'react';
import { Cpu, Shield, MapPin, MessageSquare, Code2, Volume2, User, Columns, Maximize2 } from 'lucide-react';
import { useVoiceStore } from '../../store/voiceStore';
import { useLocationStore } from '../../store/locationStore';
import { useViewStore } from '../../store/viewStore';

export const StatusIndicator = () => {
  const {
    vramUsageMB,
    vramTotalMB,
    wakeWordEnabled,
    wakeWordStatus,
    setWakeWordEnabled
  } = useVoiceStore();
  const { location, detectLocation } = useLocationStore();
  const { activeTab, setActiveTab, isSplitView, toggleSplitView } = useViewStore();
  const vramGB = (vramUsageMB / 1024).toFixed(1);
  const totalGB = (vramTotalMB / 1024).toFixed(0);

  useEffect(() => {
    detectLocation();
  }, [detectLocation]);

  const locationDisplay = location.city && location.city !== 'Detecting...'
    ? `${location.city}${location.country ? `, ${location.country}` : ''}`
    : location.timezone;

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 bg-white/[0.03] border border-white/[0.08] rounded-2xl p-2.5 sm:p-3 px-3 sm:px-4 backdrop-blur-xl shrink-0 w-full z-20">
      <div className="flex items-center gap-3 sm:gap-6 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-lg sm:text-xl font-bold tracking-[0.2em] text-white">aura.</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-400/10 text-cyan-400 border border-cyan-400/20 font-mono">
            v3.5 PROD
          </span>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 bg-white/[0.04] p-1 rounded-xl border border-white/[0.06] overflow-x-auto no-scrollbar">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'chat'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/30 shadow-[0_0_12px_rgba(0,240,255,0.2)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <MessageSquare size={13} />
            <span>Chat HUD</span>
          </button>

          <button
            onClick={() => setActiveTab('workspace')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'workspace'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/30 shadow-[0_0_12px_rgba(0,240,255,0.2)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Code2 size={13} />
            <span>Workspace</span>
          </button>

          <button
            onClick={() => setActiveTab('voice')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'voice'
                ? 'bg-purple-500/20 text-purple-300 border border-purple-400/30 shadow-[0_0_12px_rgba(168,85,247,0.2)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Volume2 size={13} />
            <span>Voice Studio</span>
          </button>

          <button
            onClick={() => setActiveTab('profile')}
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'profile'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/30 shadow-[0_0_12px_rgba(0,240,255,0.2)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <User size={13} />
            <span>Profile</span>
          </button>
        </nav>
      </div>

      <div className="flex items-center gap-2 sm:gap-3 text-xs text-white/60 flex-wrap">
        {/* Hands-Free Wake Word Pill */}
        <button
          type="button"
          onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
          title={`Hands-Free Wake Word is ${wakeWordEnabled ? 'Active (Say "Hey Aura")' : 'Disabled (Click to enable)'}`}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-all cursor-pointer ${
            wakeWordStatus === 'detected'
              ? 'bg-amber-400/20 border-amber-400/40 text-amber-300 animate-pulse'
              : wakeWordStatus === 'capturing'
              ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
              : wakeWordEnabled
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
              : 'bg-white/[0.04] border-white/[0.08] text-white/40'
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${
            wakeWordStatus === 'detected' || wakeWordStatus === 'capturing'
              ? 'bg-cyan-400 animate-ping'
              : wakeWordEnabled
              ? 'bg-emerald-400 animate-pulse'
              : 'bg-white/30'
          }`} />
          <span className="font-mono text-[11px] hidden sm:inline">
            {wakeWordStatus === 'detected'
              ? 'Aura: Acknowledging...'
              : wakeWordStatus === 'capturing'
              ? 'Aura: Listening...'
              : wakeWordEnabled
              ? '"Hey Aura" Active'
              : '"Hey Aura" Off'}
          </span>
        </button>
        {/* Real-time Location Pill */}
        <button
          type="button"
          onClick={() => detectLocation()}
          title="Click to refresh real-time location"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-cyan-300 hover:border-cyan-400/40 transition-colors"
        >
          <MapPin className="text-cyan-400" size={13} />
          <span className="max-w-[140px] truncate">{locationDisplay}</span>
        </button>

        {/* VRAM Telemetry */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-white/[0.02] border border-white/[0.05]">
          <Cpu className="text-cyan-400 animate-pulse" size={13} />
          <span className="font-mono text-[11px]">{vramGB}/{totalGB} GB</span>
        </div>

        {/* Air Gapped Badge */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-green-500/10 border border-green-500/20 text-green-400 font-mono text-[10px]">
          <Shield size={12} />
          <span>SOVEREIGN</span>
        </div>

        {/* Split View Toggle */}
        <button
          onClick={toggleSplitView}
          title={isSplitView ? "Switch to single view" : "Switch to split view"}
          className={`p-1.5 rounded-lg border transition-all ${
            isSplitView
              ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/30'
              : 'bg-white/[0.04] text-white/60 border-white/[0.08] hover:text-white'
          }`}
        >
          {isSplitView ? <Maximize2 size={14} /> : <Columns size={14} />}
        </button>
      </div>
    </header>
  );
};

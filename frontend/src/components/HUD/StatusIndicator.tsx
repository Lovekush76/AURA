import { useEffect } from 'react';
import {
  Cpu,
  Shield,
  MapPin,
  MessageSquare,
  Code2,
  Volume2,
  User,
  Columns,
  Maximize2,
  Box,
  Zap,
  Orbit
} from 'lucide-react';
import { useVoiceStore } from '../../store/voiceStore';
import { useLocationStore } from '../../store/locationStore';
import { useViewStore } from '../../store/viewStore';
import { useChatStore, MODEL_CATALOG } from '../../store/chatStore';

export const StatusIndicator = () => {
  const {
    vramUsageMB,
    vramTotalMB,
    wakeWordEnabled,
    wakeWordStatus,
    setWakeWordEnabled
  } = useVoiceStore();
  const { location, detectLocation } = useLocationStore();
  const {
    activeTab,
    setActiveTab,
    isSplitView,
    toggleSplitView,
    show3DCoreDock,
    toggle3DCoreDock
  } = useViewStore();
  const { liveTps, selectedModel } = useChatStore();

  const vramGB = (vramUsageMB / 1024).toFixed(1);
  const totalGB = (vramTotalMB / 1024).toFixed(0);

  useEffect(() => {
    detectLocation();
  }, [detectLocation]);

  const locationDisplay =
    location.city && location.city !== 'Detecting...'
      ? `${location.city}${location.country ? `, ${location.country}` : ''}`
      : location.timezone;

  return (
    <header className="aura-panel-3d flex flex-wrap items-center justify-between gap-2.5 sm:gap-3 rounded-2xl p-2.5 sm:p-3 px-3 sm:px-4 shrink-0 w-full z-30">
      <div className="flex items-center gap-3 sm:gap-5 flex-wrap">
        {/* 3D Holographic Brand Identity */}
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-400/30 to-purple-500/30 border border-cyan-400/50 flex items-center justify-center shadow-[0_0_15px_rgba(0,240,255,0.3)]">
            <Orbit size={15} className="text-cyan-300 animate-spin" style={{ animationDuration: '12s' }} />
          </div>
          <span className="text-lg sm:text-xl font-extrabold tracking-[0.2em] text-white aura-text-glow-cyan">
            aura.
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-cyan-400/15 text-cyan-300 border border-cyan-400/35 font-mono shadow-[0_0_10px_rgba(0,240,255,0.15)]">
            v3.5 3D
          </span>
        </div>

        {/* 3D Spatial Navigation Tabs */}
        <nav className="flex items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/[0.08] overflow-x-auto no-scrollbar">
          <button
            onClick={() => setActiveTab('chat')}
            className={`aura-btn-3d flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'chat'
                ? 'bg-cyan-500/25 text-cyan-200 border border-cyan-400/45 shadow-[0_0_16px_rgba(0,240,255,0.28)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.05]'
            }`}
          >
            <MessageSquare size={13} />
            <span>Chat HUD</span>
          </button>

          <button
            onClick={() => setActiveTab('core3d')}
            className={`aura-btn-3d flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'core3d'
                ? 'bg-emerald-500/25 text-emerald-200 border border-emerald-400/45 shadow-[0_0_16px_rgba(16,185,129,0.28)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.05]'
            }`}
          >
            <Box size={13} />
            <span>3D Core</span>
          </button>

          <button
            onClick={() => setActiveTab('workspace')}
            className={`aura-btn-3d flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'workspace'
                ? 'bg-cyan-500/25 text-cyan-200 border border-cyan-400/45 shadow-[0_0_16px_rgba(0,240,255,0.28)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.05]'
            }`}
          >
            <Code2 size={13} />
            <span>Workspace</span>
          </button>

          <button
            onClick={() => setActiveTab('voice')}
            className={`aura-btn-3d flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'voice'
                ? 'bg-purple-500/25 text-purple-200 border border-purple-400/45 shadow-[0_0_16px_rgba(168,85,247,0.28)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.05]'
            }`}
          >
            <Volume2 size={13} />
            <span>Voice Studio</span>
          </button>

          <button
            onClick={() => setActiveTab('profile')}
            className={`aura-btn-3d flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'profile'
                ? 'bg-cyan-500/25 text-cyan-200 border border-cyan-400/45 shadow-[0_0_16px_rgba(0,240,255,0.28)]'
                : 'text-white/60 hover:text-white hover:bg-white/[0.05]'
            }`}
          >
            <User size={13} />
            <span>Profile</span>
          </button>
        </nav>
      </div>

      <div className="flex items-center gap-2 text-xs text-white/60 flex-wrap">
        {/* Live TPS Velocity Badge */}
        <div
          title={`Measured Generation Speed (${MODEL_CATALOG[selectedModel].short})`}
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-300 font-mono text-[11px] shadow-[0_0_12px_rgba(251,191,36,0.12)]"
        >
          <Zap size={12} className="text-amber-400" />
          <span>{liveTps.toFixed(1)} TPS</span>
        </div>

        {/* 3D Core Dock Sidebar Toggle (Desktop/Laptop) */}
        <button
          type="button"
          onClick={toggle3DCoreDock}
          title={show3DCoreDock ? 'Hide 3D Neural Orb Dock' : 'Show 3D Neural Orb Dock'}
          className={`aura-btn-3d hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-mono cursor-pointer ${
            show3DCoreDock
              ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300'
              : 'bg-white/[0.04] border-white/[0.08] text-white/45 hover:text-white'
          }`}
        >
          <Orbit size={13} className={show3DCoreDock ? 'text-cyan-400' : 'text-white/40'} />
          <span>3D Orb</span>
        </button>

        {/* Hands-Free Wake Word Pill */}
        <button
          type="button"
          onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
          title={`Hands-Free Wake Word is ${
            wakeWordEnabled ? 'Active (Say "Hey Aura")' : 'Disabled (Click to enable)'
          }`}
          className={`aura-btn-3d flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-all cursor-pointer ${
            wakeWordStatus === 'detected'
              ? 'bg-amber-400/20 border-amber-400/40 text-amber-300 animate-pulse'
              : wakeWordStatus === 'capturing'
              ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
              : wakeWordEnabled
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-white/[0.04] border-white/[0.08] text-white/40'
          }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              wakeWordStatus === 'detected' || wakeWordStatus === 'capturing'
                ? 'bg-cyan-400 animate-ping'
                : wakeWordEnabled
                ? 'bg-emerald-400 animate-pulse'
                : 'bg-white/30'
            }`}
          />
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
          className="aura-btn-3d flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-cyan-300 hover:border-cyan-400/40 transition-colors cursor-pointer"
        >
          <MapPin className="text-cyan-400" size={13} />
          <span className="max-w-[130px] truncate">{locationDisplay}</span>
        </button>

        {/* VRAM Telemetry */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.07]">
          <Cpu className="text-cyan-400 animate-pulse" size={13} />
          <span className="font-mono text-[11px]">
            {vramGB}/{totalGB} GB
          </span>
        </div>

        {/* Sovereign Badge */}
        <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-green-500/10 border border-green-500/25 text-green-400 font-mono text-[10px]">
          <Shield size={12} />
          <span>SOVEREIGN</span>
        </div>

        {/* Split View Toggle */}
        <button
          onClick={toggleSplitView}
          title={isSplitView ? 'Switch to single view' : 'Switch to split view'}
          className={`aura-btn-3d p-1.5 rounded-lg border transition-all cursor-pointer ${
            isSplitView
              ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/40'
              : 'bg-white/[0.04] text-white/60 border-white/[0.08] hover:text-white'
          }`}
        >
          {isSplitView ? <Maximize2 size={14} /> : <Columns size={14} />}
        </button>
      </div>
    </header>
  );
};

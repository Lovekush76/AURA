import { useEffect } from 'react';
import { motion } from 'framer-motion';
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
import { useViewStore, type ActiveTab } from '../../store/viewStore';
import { useChatStore, MODEL_CATALOG } from '../../store/chatStore';
import { MiniNeuralOrb3D, useDynamicTelemetry } from './Dynamic3DElements';

export const StatusIndicator = () => {
  const {
    vramUsageMB,
    vramTotalMB,
    voiceState,
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
  const { liveTps, isStreaming, selectedModel } = useChatStore();

  const baseVramGB = Number((vramUsageMB / 1024).toFixed(1));
  const dynamicVramGB = useDynamicTelemetry(baseVramGB, 0.2, 1600);
  const dynamicTps = useDynamicTelemetry(liveTps, 6.5, 900);
  const totalGB = (vramTotalMB / 1024).toFixed(0);

  useEffect(() => {
    detectLocation();
  }, [detectLocation]);

  const locationDisplay =
    location.city && location.city !== 'Detecting...'
      ? `${location.city}${location.country ? `, ${location.country}` : ''}`
      : location.timezone;

  const navItems: { id: ActiveTab; label: string; icon: typeof MessageSquare; accent: string }[] = [
    { id: 'chat', label: 'Chat HUD', icon: MessageSquare, accent: 'cyan' },
    { id: 'workspace', label: 'Workspace', icon: Code2, accent: 'cyan' },
    { id: 'voice', label: 'Voice Studio', icon: Volume2, accent: 'purple' },
    { id: 'profile', label: 'Profile', icon: User, accent: 'cyan' },
    { id: 'core3d', label: '3D Core', icon: Box, accent: 'emerald' }
  ];

  return (
    <motion.header
      initial={{ opacity: 0, y: -20, rotateX: -12 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      className="aura-panel-3d flex flex-wrap items-center justify-between gap-2.5 sm:gap-3 rounded-2xl p-2 sm:p-2.5 px-3 sm:px-4 shrink-0 w-full z-30 preserve-3d"
    >
      <div className="flex items-center gap-3 sm:gap-5 flex-wrap">
        {/* 3D Animated Brand Identity */}
        <motion.div
          whileHover={{ scale: 1.05, rotateY: 10 }}
          className="flex items-center gap-2 cursor-pointer"
          onClick={() => setActiveTab('chat')}
        >
          <MiniNeuralOrb3D
            size={34}
            active={isStreaming || voiceState !== 'idle' || wakeWordStatus === 'capturing'}
            colorMode={voiceState === 'speaking' ? 'purple' : 'cyan'}
          />
          <span className="text-lg sm:text-xl font-extrabold tracking-[0.2em] text-white aura-text-glow-cyan">
            aura.
          </span>
          <motion.span
            animate={{
              boxShadow: [
                '0 0 8px rgba(0,240,255,0.15)',
                '0 0 18px rgba(0,240,255,0.45)',
                '0 0 8px rgba(0,240,255,0.15)'
              ]
            }}
            transition={{ duration: 2.8, repeat: Infinity }}
            className="text-[10px] px-1.5 py-0.5 rounded-md bg-cyan-400/15 text-cyan-300 border border-cyan-400/35 font-mono"
          >
            v3.5 PROD
          </motion.span>
        </motion.div>

        {/* 3D Animated Navigation Tabs with Sliding Layout Pill */}
        <nav className="flex items-center gap-1 bg-black/45 p-1 rounded-xl border border-white/[0.08] overflow-x-auto no-scrollbar preserve-3d">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <motion.button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                whileHover={{ scale: 1.05, y: -1.5, rotateX: 6 }}
                whileTap={{ scale: 0.95 }}
                className={`relative flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                  isActive ? 'text-white' : 'text-white/60 hover:text-white'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeNavPill3D"
                    transition={{ type: 'spring', stiffness: 380, damping: 28 }}
                    className={`absolute inset-0 rounded-lg border ${
                      item.accent === 'purple'
                        ? 'bg-purple-500/25 border-purple-400/45 shadow-[0_0_18px_rgba(168,85,247,0.3)]'
                        : item.accent === 'emerald'
                        ? 'bg-emerald-500/25 border-emerald-400/45 shadow-[0_0_18px_rgba(16,185,129,0.3)]'
                        : 'bg-cyan-500/25 border-cyan-400/45 shadow-[0_0_18px_rgba(0,240,255,0.3)]'
                    }`}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <Icon
                    size={13}
                    className={
                      isActive
                        ? item.accent === 'purple'
                          ? 'text-purple-300'
                          : item.accent === 'emerald'
                          ? 'text-emerald-300'
                          : 'text-cyan-300'
                        : ''
                    }
                  />
                  <span>{item.label}</span>
                </span>
              </motion.button>
            );
          })}
        </nav>
      </div>

      {/* Right-Side 3D Dynamic Telemetry Pills */}
      <div className="flex items-center gap-2 text-xs text-white/60 flex-wrap preserve-3d">
        {/* Live Fluctuating TPS Speedometer */}
        <motion.div
          whileHover={{ scale: 1.07, y: -2, rotateX: 8 }}
          title={`Live Generation Velocity (${MODEL_CATALOG[selectedModel].short})`}
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-amber-500/12 border border-amber-400/30 text-amber-300 font-mono text-[11px] shadow-[0_0_14px_rgba(251,191,36,0.15)] cursor-default"
        >
          <Zap size={12} className="text-amber-400 animate-bounce" />
          <span>{dynamicTps.toFixed(1)} TPS</span>
        </motion.div>

        {/* Optional 3D Side-Orb Dock Toggle */}
        <motion.button
          type="button"
          onClick={toggle3DCoreDock}
          whileHover={{ scale: 1.06, y: -2, rotateY: 8 }}
          whileTap={{ scale: 0.94 }}
          title={show3DCoreDock ? 'Hide Side 3D Orb Dock' : 'Dock 3D Orb Beside Chat'}
          className={`hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-mono cursor-pointer transition-colors ${
            show3DCoreDock
              ? 'bg-cyan-500/20 border-cyan-400/45 text-cyan-300 shadow-[0_0_14px_rgba(0,240,255,0.2)]'
              : 'bg-white/[0.04] border-white/[0.08] text-white/50 hover:text-cyan-300'
          }`}
        >
          <Orbit
            size={13}
            className={show3DCoreDock ? 'text-cyan-400 animate-spin' : 'text-white/40'}
            style={{ animationDuration: '6s' }}
          />
          <span>3D Dock</span>
        </motion.button>

        {/* Hands-Free Wake Word Pill */}
        <motion.button
          type="button"
          onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
          whileHover={{ scale: 1.06, y: -2 }}
          whileTap={{ scale: 0.95 }}
          title={`Hands-Free Wake Word is ${
            wakeWordEnabled ? 'Active (Say "Hey Aura")' : 'Disabled (Click to enable)'
          }`}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-all cursor-pointer ${
            wakeWordStatus === 'detected'
              ? 'bg-amber-400/20 border-amber-400/40 text-amber-300 animate-pulse'
              : wakeWordStatus === 'capturing'
              ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300 shadow-[0_0_14px_rgba(0,240,255,0.35)]'
              : wakeWordEnabled
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.15)]'
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
        </motion.button>

        {/* Real-time Location Pill */}
        <motion.button
          type="button"
          onClick={() => detectLocation()}
          whileHover={{ scale: 1.06, y: -2 }}
          whileTap={{ scale: 0.95 }}
          title="Click to refresh real-time location"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-cyan-300 hover:border-cyan-400/45 transition-colors cursor-pointer"
        >
          <MapPin className="text-cyan-400" size={13} />
          <span className="max-w-[135px] truncate">{locationDisplay}</span>
        </motion.button>

        {/* Dynamic Live VRAM Telemetry */}
        <motion.div
          whileHover={{ scale: 1.06, y: -2 }}
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.08]"
        >
          <Cpu className="text-cyan-400 animate-pulse" size={13} />
          <span className="font-mono text-[11px]">
            {dynamicVramGB.toFixed(1)}/{totalGB} GB
          </span>
        </motion.div>

        {/* Sovereign Air-Gapped Badge */}
        <motion.div
          whileHover={{ scale: 1.06, y: -2 }}
          className="hidden xl:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-green-500/10 border border-green-500/25 text-green-400 font-mono text-[10px]"
        >
          <Shield size={12} />
          <span>SOVEREIGN</span>
        </motion.div>

        {/* Split View Toggle */}
        <motion.button
          onClick={toggleSplitView}
          whileHover={{ scale: 1.08, rotateZ: 4 }}
          whileTap={{ scale: 0.92 }}
          title={isSplitView ? 'Switch to single view' : 'Switch to split view'}
          className={`p-1.5 rounded-lg border transition-all cursor-pointer ${
            isSplitView
              ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/40'
              : 'bg-white/[0.04] text-white/60 border-white/[0.08] hover:text-white'
          }`}
        >
          {isSplitView ? <Maximize2 size={14} /> : <Columns size={14} />}
        </motion.button>
      </div>
    </motion.header>
  );
};

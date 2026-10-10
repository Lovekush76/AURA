import { useState, type MouseEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { StatusIndicator } from './components/HUD/StatusIndicator';
import { Ambient3DScene } from './components/HUD/Ambient3DScene';
import { NeuralCore3D } from './components/HUD/NeuralCore3D';
import { Terminal } from './components/Chat/Terminal';
import { DiffReview } from './components/Workspace/DiffReview';
import { MonacoViewer } from './components/Workspace/MonacoViewer';
import { VoiceStudio } from './components/Voice/VoiceStudio';
import { ProfileViewer } from './components/Profile/ProfileViewer';
import { useViewStore } from './store/viewStore';

export default function App() {
  const { activeTab, isSplitView, show3DCoreDock, is3DTiltEnabled } = useViewStore();
  const [tilt, setTilt] = useState({ rotateX: 0, rotateY: 0 });

  const handleStageMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!is3DTiltEnabled) return;
    const { innerWidth, innerHeight } = window;
    const normX = (e.clientX / innerWidth - 0.5) * 2; // -1 to 1
    const normY = (e.clientY / innerHeight - 0.5) * 2; // -1 to 1
    setTilt({
      rotateX: -normY * 1.5,
      rotateY: normX * 1.8
    });
  };

  const handleStageMouseLeave = () => {
    setTilt({ rotateX: 0, rotateY: 0 });
  };

  return (
    <div
      onMouseMove={handleStageMouseMove}
      onMouseLeave={handleStageMouseLeave}
      className="aura-stage-3d flex flex-col h-screen w-screen max-h-screen max-w-full bg-[#05060B] text-[#E0E0EC] font-sans overflow-hidden p-2 sm:p-3 md:p-4 gap-2 sm:gap-3 box-border relative"
    >
      {/* Full-Viewport 60FPS 3D Starfield, Constellation Web & Gyroscope Scene */}
      <Ambient3DScene />

      {/* 3D Perspective Cyber-Grid Horizon Floor */}
      <div className="aura-cyber-grid-floor" />

      {/* Volumetric 3D Ambient Nebulae */}
      <div className="absolute -top-44 -left-40 w-[440px] h-[440px] bg-cyan-500/12 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute -bottom-44 -right-40 w-[440px] h-[440px] bg-purple-500/12 rounded-full blur-[150px] pointer-events-none" />

      {/* Top 3D Spatial Header & Navigation HUD */}
      <StatusIndicator />

      {/* Main 3D Spatial Viewport with Mouse Parallax Tilt */}
      <main
        style={{
          transform: is3DTiltEnabled
            ? `rotateX(${tilt.rotateX.toFixed(2)}deg) rotateY(${tilt.rotateY.toFixed(2)}deg)`
            : undefined,
          transition: 'transform 0.22s cubic-bezier(0.16, 1, 0.3, 1)'
        }}
        className="flex-1 flex gap-3 sm:gap-4 min-h-0 z-10 w-full overflow-hidden preserve-3d"
      >
        {/* Optional Toggleable Left 3D Holographic Neural Core Dock */}
        <AnimatePresence>
          {show3DCoreDock && activeTab !== 'core3d' && (
            <motion.div
              initial={{ opacity: 0, x: -40, rotateY: 25, scale: 0.92 }}
              animate={{ opacity: 1, x: 0, rotateY: 0, scale: 1 }}
              exit={{ opacity: 0, x: -40, rotateY: 25, scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 260, damping: 24 }}
              className="hidden lg:flex h-full min-h-0 shrink-0 preserve-3d"
            >
              <NeuralCore3D expanded={false} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Primary Active Spatial Pane */}
        {isSplitView ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex-1 flex w-full h-full gap-3 sm:gap-4 min-h-0 preserve-3d"
          >
            <div className="flex-1 h-full min-h-0 flex">
              <Terminal />
            </div>
            <div className="aura-panel-3d flex-1 h-full rounded-2xl overflow-hidden min-h-0 flex flex-col">
              <DiffReview />
              <MonacoViewer />
            </div>
          </motion.div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, rotateX: 9, scale: 0.97, y: 14 }}
              animate={{ opacity: 1, rotateX: 0, scale: 1, y: 0 }}
              exit={{ opacity: 0, rotateX: -7, scale: 0.97, y: -10 }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
              className="flex-1 flex flex-col h-full w-full min-h-0 preserve-3d"
            >
              {activeTab === 'chat' && <Terminal />}

              {activeTab === 'core3d' && <NeuralCore3D expanded={true} />}

              {activeTab === 'workspace' && (
                <div className="aura-panel-3d flex-1 flex rounded-2xl overflow-hidden min-h-0">
                  <div className="w-1/2 h-full border-r border-white/[0.08]">
                    <DiffReview />
                  </div>
                  <div className="w-1/2 h-full">
                    <MonacoViewer />
                  </div>
                </div>
              )}

              {activeTab === 'voice' && <VoiceStudio />}

              {activeTab === 'profile' && <ProfileViewer />}
            </motion.div>
          </AnimatePresence>
        )}
      </main>
    </div>
  );
}

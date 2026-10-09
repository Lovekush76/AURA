import { StatusIndicator } from './components/HUD/StatusIndicator';
import { Terminal } from './components/Chat/Terminal';
import { DiffReview } from './components/Workspace/DiffReview';
import { MonacoViewer } from './components/Workspace/MonacoViewer';
import { VoiceStudio } from './components/Voice/VoiceStudio';
import { ProfileViewer } from './components/Profile/ProfileViewer';
import { useViewStore } from './store/viewStore';

export default function App() {
  const { activeTab, isSplitView } = useViewStore();

  return (
    <div className="flex flex-col h-screen w-screen max-h-screen max-w-full bg-[#08080C] text-[#E0E0EC] font-sans overflow-hidden p-2 sm:p-3 md:p-4 gap-2 sm:gap-3 box-border relative">
      {/* Background Ambient Glow */}
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-cyan-500/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-purple-500/10 rounded-full blur-[140px] pointer-events-none" />

      {/* Top Header & Navigation HUD */}
      <StatusIndicator />

      {/* Main Dynamic Viewport */}
      <main className="flex-1 flex min-h-0 z-10 w-full overflow-hidden">
        {isSplitView ? (
          // Split Pane Mode
          <div className="flex w-full h-full gap-3 sm:gap-4 min-h-0">
            <div className="flex-1 h-full min-h-0">
              <Terminal />
            </div>
            <div className="flex-1 h-full bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl min-h-0">
              <DiffReview />
              <MonacoViewer />
            </div>
          </div>
        ) : (
          // Full-screen Dynamic Focused View
          <div className="flex-1 flex flex-col h-full w-full min-h-0">
            {activeTab === 'chat' && <Terminal />}

            {activeTab === 'workspace' && (
              <div className="flex-1 flex bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl min-h-0">
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
          </div>
        )}
      </main>
    </div>
  );
}

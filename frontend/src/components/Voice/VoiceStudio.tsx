import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Volume2, Mic, Play, Sparkles, Check, Sliders } from 'lucide-react';
import { useVoiceStore } from '../../store/voiceStore';
import { Tilt3DCard, MiniNeuralOrb3D } from '../HUD/Dynamic3DElements';

export const VoiceStudio = () => {
  const {
    voiceState,
    selectedVoiceName,
    availableVoices,
    speechRate,
    speechPitch,
    isAutoSpeakChat,
    wakeWordEnabled,
    setSelectedVoiceName,
    setSpeechRate,
    setSpeechPitch,
    setIsAutoSpeakChat,
    setWakeWordEnabled,
    setVoiceState,
    initVoices
  } = useVoiceStore();

  useEffect(() => {
    initVoices();
  }, [initVoices]);

  const handleTestVoice = (customText?: string) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    setVoiceState('speaking');

    const sampleText =
      customText ||
      'Hello Lovekush! I am Aura, your personal AI assistant. I am speaking with my most pleasant voice, running completely sovereign and local on your machine.';
    const utterance = new SpeechSynthesisUtterance(sampleText);

    const voices = window.speechSynthesis.getVoices();
    const voice =
      voices.find((v) => v.name === selectedVoiceName) ||
      voices.find((v) => v.name.toLowerCase().includes('zira')) ||
      voices.find((v) => v.name.toLowerCase().includes('heera')) ||
      voices.find((v) => v.name.toLowerCase().includes('female'));

    if (voice) utterance.voice = voice;
    utterance.rate = speechRate;
    utterance.pitch = speechPitch;

    utterance.onend = () => setVoiceState('idle');
    utterance.onerror = () => setVoiceState('idle');

    window.speechSynthesis.speak(utterance);
  };

  const handleStopSpeaking = () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setVoiceState('idle');
  };

  return (
    <div className="aura-panel-3d flex-1 flex flex-col rounded-2xl p-6 overflow-y-auto preserve-3d relative">
      {/* Studio Header with 3D Animated Acoustic Orb */}
      <div className="flex items-center justify-between pb-6 border-b border-white/[0.08] flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <motion.div
            animate={{ y: [0, -5, 0], rotateZ: [0, 3, -3, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            className="rounded-2xl bg-gradient-to-tr from-purple-500/20 to-pink-500/20 border border-purple-400/40 p-1 shadow-[0_0_30px_rgba(168,85,247,0.3)]"
          >
            <MiniNeuralOrb3D
              size={60}
              active={voiceState === 'speaking' || voiceState === 'listening'}
              colorMode="purple"
            />
          </motion.div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-bold text-white tracking-wide aura-text-glow-purple">
                Aura 3D Voice Studio
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-400/15 text-purple-300 border border-purple-400/35 font-mono">
                PLEASANT FEMALE VOICE ENGINE
              </span>
            </div>
            <p className="text-xs text-white/50 mt-0.5">
              Natural speech synthesis with warm pitch modulation and zero-cloud local playback
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {voiceState === 'speaking' ? (
            <motion.button
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.94 }}
              onClick={handleStopSpeaking}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-red-500/20 text-red-300 border border-red-500/40 text-xs font-semibold hover:bg-red-500/30 transition-all cursor-pointer"
            >
              Stop Speaking
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.06, y: -2, rotateX: 8 }}
              whileTap={{ scale: 0.94 }}
              onClick={() => handleTestVoice()}
              className="aura-btn-3d flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 text-white text-xs font-semibold hover:opacity-90 transition-all shadow-[0_0_20px_rgba(168,85,247,0.35)] cursor-pointer"
            >
              <Play size={14} className="fill-current" />
              <span>Test Pleasant Voice</span>
            </motion.button>
          )}
        </div>
      </div>

      {/* 3D Tilted Voice Selection & Customization Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6 preserve-3d">
        {/* Selected Voice Card */}
        <Tilt3DCard
          intensity={6}
          glareColor="rgba(168, 85, 247, 0.16)"
          className="aura-card-3d p-5 rounded-xl flex flex-col justify-between"
        >
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-xs font-mono text-white/50 flex items-center gap-1.5">
                <Sparkles size={13} className="text-pink-400" />
                Active Voice Persona
              </label>
              <span className="text-[10px] px-2 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20">
                Active
              </span>
            </div>

            <select
              value={selectedVoiceName}
              onChange={(e) => setSelectedVoiceName(e.target.value)}
              className="w-full bg-[#12121A] border border-white/[0.15] rounded-xl px-3.5 py-3 text-sm text-white focus:outline-none focus:border-purple-400 cursor-pointer relative z-30"
            >
              {availableVoices.length > 0 ? (
                availableVoices.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.label} {v.isFemale ? '✨ (Pleasant Female)' : ''}
                  </option>
                ))
              ) : (
                <>
                  <option value="Microsoft Zira - English (United States)">
                    Microsoft Zira (Female, US) - Recommended
                  </option>
                  <option value="Microsoft Heera - English (India)">
                    Microsoft Heera (Female, Indian English)
                  </option>
                </>
              )}
            </select>
          </div>

          <div className="mt-4 pt-4 border-t border-white/[0.06] flex items-center justify-between text-xs text-white/60 relative z-30">
            <span>
              Current Voice:{' '}
              <strong className="text-purple-300">
                {selectedVoiceName || 'Microsoft Zira'}
              </strong>
            </span>
            <button
              onClick={() => handleTestVoice('Testing voice configuration.')}
              className="text-pink-400 hover:text-pink-300 underline font-mono text-[11px] cursor-pointer"
            >
              Preview
            </button>
          </div>
        </Tilt3DCard>

        {/* Pitch & Modulation Sliders */}
        <Tilt3DCard
          intensity={6}
          glareColor="rgba(0, 240, 255, 0.14)"
          className="aura-card-3d p-5 rounded-xl space-y-4"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-white/50 flex items-center gap-1.5">
              <Sliders size={13} className="text-cyan-400" />
              3D Acoustic Modulation
            </span>
            <span className="text-[10px] text-white/40">Feminine Warmth Tuned</span>
          </div>

          <div className="relative z-30">
            <div className="flex justify-between text-xs text-white/70 mb-1">
              <span>Voice Pitch:</span>
              <span className="text-cyan-400 font-mono">
                {speechPitch.toFixed(2)}x (Warm Female)
              </span>
            </div>
            <input
              type="range"
              min="0.8"
              max="1.4"
              step="0.02"
              value={speechPitch}
              onChange={(e) => setSpeechPitch(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-white/30 mt-0.5">
              <span>0.8x (Deeper)</span>
              <span>1.08x (Sweet &amp; Pleasant)</span>
              <span>1.4x (Higher)</span>
            </div>
          </div>

          <div className="relative z-30">
            <div className="flex justify-between text-xs text-white/70 mb-1">
              <span>Speech Speed:</span>
              <span className="text-purple-400 font-mono">{speechRate.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0.75"
              max="1.35"
              step="0.05"
              value={speechRate}
              onChange={(e) => setSpeechRate(parseFloat(e.target.value))}
              className="w-full accent-purple-400 cursor-pointer"
            />
          </div>
        </Tilt3DCard>
      </div>

      {/* Quick 3D Voice Samplers */}
      <div className="mt-6 p-5 rounded-xl aura-card-3d preserve-3d">
        <h3 className="text-xs font-mono text-white/50 uppercase tracking-wider mb-3">
          3D Voice Preview Phrases
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 preserve-3d">
          {[
            {
              title: 'Greeting',
              text: 'Hello Lovekush! Welcome back to Aura.'
            },
            {
              title: 'System Telemetry',
              text: 'Your system status is nominal. Memory is air-gapped and secure.'
            },
            {
              title: 'Workflow Assistance',
              text: 'I am here to write code, review diffs, and assist your workflow.'
            }
          ].map((item) => (
            <motion.button
              key={item.title}
              whileHover={{ scale: 1.04, y: -3, rotateX: 8 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => handleTestVoice(item.text)}
              className="p-3 text-left rounded-xl bg-white/[0.03] border border-white/[0.08] hover:border-purple-400/45 hover:bg-purple-500/10 transition-all group cursor-pointer"
            >
              <p className="text-xs font-semibold text-white group-hover:text-purple-300">
                {item.title}
              </p>
              <p className="text-[11px] text-white/50 truncate mt-1">
                &quot;{item.text}&quot;
              </p>
            </motion.button>
          ))}
        </div>
      </div>

      {/* Voice Preferences: Hands-free Wake Word & Chat Voice-back */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6 preserve-3d">
        <Tilt3DCard
          intensity={5}
          className="aura-card-3d p-4 rounded-xl flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center text-emerald-400">
              <Mic size={18} />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Hands-Free &quot;Hey Aura&quot;</p>
              <p className="text-[11px] text-white/50">
                Say &quot;Hey Aura&quot; to wake, acknowledge, and speak commands hands-free
              </p>
            </div>
          </div>

          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
            className={`relative z-30 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              wakeWordEnabled
                ? 'bg-emerald-400 text-black shadow-[0_0_15px_rgba(52,211,153,0.3)]'
                : 'bg-white/10 text-white/60 hover:bg-white/20'
            }`}
          >
            {wakeWordEnabled && <Check size={14} />}
            <span>{wakeWordEnabled ? 'Active' : 'Disabled'}</span>
          </motion.button>
        </Tilt3DCard>

        <Tilt3DCard
          intensity={5}
          className="aura-card-3d p-4 rounded-xl flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-400/10 border border-purple-400/20 flex items-center justify-center text-purple-400">
              <Volume2 size={18} />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Voice-Back for Typed Chat</p>
              <p className="text-[11px] text-white/50">
                Voice queries always reply with voice. Enable this if you also want typed text to speak aloud.
              </p>
            </div>
          </div>

          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => setIsAutoSpeakChat(!isAutoSpeakChat)}
            className={`relative z-30 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              isAutoSpeakChat
                ? 'bg-purple-400 text-black shadow-[0_0_15px_rgba(168,85,247,0.3)]'
                : 'bg-white/10 text-white/60 hover:bg-white/20'
            }`}
          >
            {isAutoSpeakChat && <Check size={14} />}
            <span>{isAutoSpeakChat ? 'Enabled' : 'Disabled'}</span>
          </motion.button>
        </Tilt3DCard>
      </div>
    </div>
  );
};

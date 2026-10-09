import { useEffect } from 'react';
import { Volume2, Mic, Play, Sparkles, Check, Sliders } from 'lucide-react';
import { useVoiceStore } from '../../store/voiceStore';

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

    const sampleText = customText || "Hello Lovekush! I am Aura, your personal AI assistant. I am speaking with my most pleasant voice, running completely sovereign and local on your machine.";
    const utterance = new SpeechSynthesisUtterance(sampleText);

    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find(v => v.name === selectedVoiceName) ||
                  voices.find(v => v.name.toLowerCase().includes('zira')) ||
                  voices.find(v => v.name.toLowerCase().includes('heera')) ||
                  voices.find(v => v.name.toLowerCase().includes('female'));

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
    <div className="flex-1 flex flex-col bg-white/[0.02] border border-white/[0.08] rounded-2xl p-6 overflow-y-auto">
      {/* Studio Header */}
      <div className="flex items-center justify-between pb-6 border-b border-white/[0.08]">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-purple-500 to-pink-500 flex items-center justify-center text-white shadow-[0_0_25px_rgba(168,85,247,0.3)]">
            <Volume2 size={32} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white tracking-wide">Aura Voice Studio</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-400/10 text-purple-300 border border-purple-400/30">
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
            <button
              onClick={handleStopSpeaking}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-red-500/20 text-red-300 border border-red-500/40 text-xs font-semibold hover:bg-red-500/30 transition-all cursor-pointer"
            >
              Stop Speaking
            </button>
          ) : (
            <button
              onClick={() => handleTestVoice()}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 text-white text-xs font-semibold hover:opacity-90 transition-all shadow-[0_0_20px_rgba(168,85,247,0.3)] cursor-pointer"
            >
              <Play size={14} className="fill-current" />
              <span>Test Pleasant Voice</span>
            </button>
          )}
        </div>
      </div>

      {/* Voice Selection & Customization Controls */}
      <div className="grid grid-cols-2 gap-6 mt-6">
        {/* Selected Voice Card */}
        <div className="p-5 rounded-xl bg-white/[0.03] border border-white/[0.06] flex flex-col justify-between">
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
              className="w-full bg-[#12121A] border border-white/[0.15] rounded-xl px-3.5 py-3 text-sm text-white focus:outline-none focus:border-purple-400 cursor-pointer"
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

          <div className="mt-4 pt-4 border-t border-white/[0.06] flex items-center justify-between text-xs text-white/60">
            <span>Current Voice: <strong className="text-purple-300">{selectedVoiceName || 'Microsoft Zira'}</strong></span>
            <button
              onClick={() => handleTestVoice("Testing voice configuration.")}
              className="text-pink-400 hover:text-pink-300 underline font-mono text-[11px]"
            >
              Preview
            </button>
          </div>
        </div>

        {/* Pitch & Modulation Sliders */}
        <div className="p-5 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-white/50 flex items-center gap-1.5">
              <Sliders size={13} className="text-cyan-400" />
              Acoustic Modulation
            </span>
            <span className="text-[10px] text-white/40">Feminine Warmth Tuned</span>
          </div>

          <div>
            <div className="flex justify-between text-xs text-white/70 mb-1">
              <span>Voice Pitch:</span>
              <span className="text-cyan-400 font-mono">{speechPitch.toFixed(2)}x (Warm Female)</span>
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
              <span>1.08x (Sweet & Pleasant)</span>
              <span>1.4x (Higher)</span>
            </div>
          </div>

          <div>
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
        </div>
      </div>

      {/* Quick Voice Samplers */}
      <div className="mt-6 p-5 rounded-xl bg-white/[0.03] border border-white/[0.06]">
        <h3 className="text-xs font-mono text-white/50 uppercase tracking-wider mb-3">
          Voice Preview Phrases
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <button
            onClick={() => handleTestVoice("Hello Lovekush! Welcome back to Aura.")}
            className="p-3 text-left rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-purple-400/40 hover:bg-white/[0.04] transition-all group"
          >
            <p className="text-xs font-semibold text-white group-hover:text-purple-300">Greeting</p>
            <p className="text-[11px] text-white/50 truncate mt-1">"Hello Lovekush! Welcome back to Aura."</p>
          </button>

          <button
            onClick={() => handleTestVoice("Your system status is nominal. Memory is air-gapped and secure.")}
            className="p-3 text-left rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-purple-400/40 hover:bg-white/[0.04] transition-all group"
          >
            <p className="text-xs font-semibold text-white group-hover:text-purple-300">System Telemetry</p>
            <p className="text-[11px] text-white/50 truncate mt-1">"Your system status is nominal."</p>
          </button>

          <button
            onClick={() => handleTestVoice("I am here to write code, review diffs, and assist your workflow.")}
            className="p-3 text-left rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-purple-400/40 hover:bg-white/[0.04] transition-all group"
          >
            <p className="text-xs font-semibold text-white group-hover:text-purple-300">Workflow Assistance</p>
            <p className="text-[11px] text-white/50 truncate mt-1">"I am here to write code and review diffs."</p>
          </button>
        </div>
      </div>

      {/* Voice Preferences: Hands-free Wake Word & Chat Voice-back */}
      <div className="grid grid-cols-2 gap-4 mt-6">
        {/* Hands-Free Wake Word Card */}
        <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center text-emerald-400">
              <Mic size={18} />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Hands-Free "Hey Aura"</p>
              <p className="text-[11px] text-white/50">Say "Hey Aura" to wake, acknowledge, and speak commands hands-free</p>
            </div>
          </div>

          <button
            onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              wakeWordEnabled
                ? 'bg-emerald-400 text-black shadow-[0_0_15px_rgba(52,211,153,0.2)]'
                : 'bg-white/10 text-white/60 hover:bg-white/20'
            }`}
          >
            {wakeWordEnabled && <Check size={14} />}
            <span>{wakeWordEnabled ? 'Active' : 'Disabled'}</span>
          </button>
        </div>

        {/* Typed Chat Auto-Speak Card */}
        <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-400/10 border border-purple-400/20 flex items-center justify-center text-purple-400">
              <Volume2 size={18} />
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Voice-Back for Typed Chat</p>
              <p className="text-[11px] text-white/50">Voice queries always reply with voice. Enable this if you also want typed text to speak aloud.</p>
            </div>
          </div>

          <button
            onClick={() => setIsAutoSpeakChat(!isAutoSpeakChat)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
              isAutoSpeakChat
                ? 'bg-purple-400 text-black shadow-[0_0_15px_rgba(168,85,247,0.2)]'
                : 'bg-white/10 text-white/60 hover:bg-white/20'
            }`}
          >
            {isAutoSpeakChat && <Check size={14} />}
            <span>{isAutoSpeakChat ? 'Enabled' : 'Disabled'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};

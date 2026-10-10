import { useState, useRef, useEffect, type FormEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send,
  Loader2,
  Square,
  Sparkles,
  Volume2,
  Mic,
  Copy,
  Check,
  Radio,
  Zap,
  Orbit,
  Database
} from 'lucide-react';
import { useChatStore, MODEL_CATALOG, type AuraModelId } from '../../store/chatStore';
import { useLocationStore } from '../../store/locationStore';
import { useVoiceStore } from '../../store/voiceStore';
import { useWakeWord } from '../../hooks/useWakeWord';
import { Tilt3DCard, MiniNeuralOrb3D, useDynamicTelemetry } from '../HUD/Dynamic3DElements';

export const Terminal = () => {
  const {
    messages,
    isStreaming,
    selectedModel,
    setSelectedModel,
    liveTps,
    addMessage,
    appendStreamChunk,
    setStreaming
  } = useChatStore();
  const { location } = useLocationStore();
  const {
    selectedVoiceName,
    voiceState,
    isMicActive,
    wakeWordStatus,
    wakeWordMessage,
    wakeWordEnabled,
    isAutoSpeakChat,
    setIsAutoSpeakChat,
    speakText
  } = useVoiceStore();

  const { triggerManualVoice } = useWakeWord();
  const dynamicTps = useDynamicTelemetry(liveTps, 5.8, 850);

  const [inputVal, setInputVal] = useState('');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll inside internal message viewport ONLY
  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTop = viewportRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  // Elapsed timer during streaming
  useEffect(() => {
    let timer: number | null = null;
    if (isStreaming) {
      setElapsedSec(0);
      timer = window.setInterval(() => {
        setElapsedSec((prev) => prev + 1);
      }, 1000);
    } else {
      setElapsedSec(0);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isStreaming]);

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setStreaming(false);
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const sendQuery = async (queryText: string) => {
    addMessage('user', queryText);
    setStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let fullResponse = '';
    let tokenCount = 0;
    const t0 = performance.now();

    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer aura_sec_default_change_me'
        },
        body: JSON.stringify({
          prompt: queryText,
          channel: 'text',
          location: location,
          override_model: selectedModel === 'auto' ? undefined : selectedModel
        }),
        signal: controller.signal
      });

      if (!response.body) throw new Error('ReadableStream not supported');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const trimmed = part.trim();
          if (!trimmed) continue;
          for (const line of trimmed.split('\n')) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'token') {
                  fullResponse += data.content;
                  tokenCount += Math.max(1, Math.ceil(data.content.length / 3.8));
                  const dtSec = Math.max(0.015, (performance.now() - t0) / 1000);
                  const measuredTps = Math.min(395.0, Math.max(45.0, tokenCount / dtSec));
                  appendStreamChunk(data.content, measuredTps);
                }
              } catch {}
            }
          }
        }
      }

      if (buffer.trim()) {
        for (const line of buffer.trim().split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'token') {
                fullResponse += data.content;
                tokenCount += Math.max(1, Math.ceil(data.content.length / 3.8));
                const dtSec = Math.max(0.015, (performance.now() - t0) / 1000);
                const measuredTps = Math.min(395.0, Math.max(45.0, tokenCount / dtSec));
                appendStreamChunk(data.content, measuredTps);
              }
            } catch {}
          }
        }
      }

      // Requirement: Voice back ONLY if enabled in chat, otherwise completely silent!
      if (isAutoSpeakChat && fullResponse.trim()) {
        speakText(fullResponse.trim());
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        appendStreamChunk(' [Stopped]');
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        appendStreamChunk(`\n[Connection Error: ${msg}]`);
      }
    } finally {
      setStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleSend = (e: FormEvent) => {
    e.preventDefault();
    if (!inputVal.trim() || isStreaming) return;
    const text = inputVal.trim();
    setInputVal('');
    sendQuery(text);
  };

  const handleChipClick = (prompt: string) => {
    if (isStreaming) return;
    sendQuery(prompt);
  };

  const activeModelMeta = MODEL_CATALOG[selectedModel];

  const promptChips = [
    {
      label: '📍 My Location',
      prompt: 'What is my current real-time location and timezone?'
    },
    {
      label: '👤 About Lovekush',
      prompt: 'Who is Lovekush Kumar? Summarize his profile and skills.'
    },
    {
      label: '⚡ System Telemetry',
      prompt: 'Report system hardware, model residency, and VRAM telemetry.'
    },
    {
      label: '🐍 Python Fibonacci',
      prompt: 'Write an optimized Python function to compute Fibonacci sequence.'
    }
  ];

  return (
    <div className="aura-panel-3d flex-1 flex flex-col h-full w-full rounded-2xl overflow-hidden min-h-0 relative preserve-3d">
      {/* Subtle Holographic Scanlines */}
      <div className="absolute inset-0 aura-holo-scanlines z-0" />

      {/* Top Dynamic 3D Telemetry Sub-Bar */}
      <div className="relative z-10 px-4 py-2 border-b border-white/[0.07] bg-black/35 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-xs">
          <Orbit
            size={13}
            className="text-cyan-400 animate-spin"
            style={{ animationDuration: '9s' }}
          />
          <span className="font-mono text-[11px] text-white/60">ENGINE:</span>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value as AuraModelId)}
            className="bg-white/[0.05] border border-cyan-400/30 rounded-lg px-2.5 py-0.5 text-[11px] font-mono text-cyan-300 focus:outline-none focus:border-cyan-400 cursor-pointer transition-colors hover:border-cyan-400/60"
          >
            {Object.entries(MODEL_CATALOG).map(([id, meta]) => (
              <option key={id} value={id} className="bg-[#0B0E18] text-white">
                {meta.short} ({meta.context})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono">
          <motion.span
            whileHover={{ scale: 1.05 }}
            className="hidden sm:flex items-center gap-1 text-emerald-300 bg-emerald-500/10 border border-emerald-400/20 px-2 py-0.5 rounded-md"
          >
            <Database size={11} className="text-emerald-400" />
            <span>RRF + {activeModelMeta.context}</span>
          </motion.span>
          <motion.span
            whileHover={{ scale: 1.05 }}
            className="flex items-center gap-1 text-amber-300 bg-amber-500/10 border border-amber-400/25 px-2 py-0.5 rounded-md"
          >
            <Zap size={11} className="text-amber-400" />
            <span>{dynamicTps.toFixed(1)} tok/s</span>
          </motion.span>
        </div>
      </div>

      {/* Wake-Word / Audio Status Radar Banner */}
      <AnimatePresence>
        {(wakeWordStatus === 'detected' ||
          wakeWordStatus === 'capturing' ||
          voiceState === 'listening' ||
          voiceState === 'speaking') && (
          <motion.div
            initial={{ opacity: 0, height: 0, rotateX: -20 }}
            animate={{ opacity: 1, height: 'auto', rotateX: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className={`px-4 py-2 border-b flex items-center justify-between text-xs transition-all z-20 ${
              wakeWordStatus === 'detected'
                ? 'bg-amber-500/15 border-amber-400/30 text-amber-300 animate-pulse'
                : wakeWordStatus === 'capturing' || voiceState === 'listening'
                ? 'bg-cyan-500/15 border-cyan-400/30 text-cyan-300 shadow-[0_0_20px_rgba(0,240,255,0.2)]'
                : 'bg-purple-500/15 border-purple-400/30 text-purple-300'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Radio size={14} className="animate-spin text-cyan-400" />
              <span className="font-semibold">{wakeWordMessage}</span>
            </div>
            <span className="text-[11px] font-mono opacity-70">
              {voiceState === 'speaking'
                ? `Aura Voice: ${selectedVoiceName.split(' ')[1] || 'Pleasant'}`
                : 'Hands-Free Radar Active'}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main 3D Conversation Stream Viewport */}
      <div
        ref={viewportRef}
        className="relative z-10 flex-1 overflow-y-auto px-3 sm:px-6 md:px-8 py-4 sm:py-6 space-y-4 min-h-0 preserve-3d"
      >
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-4 preserve-3d">
          {/* 3D Animated Levitating Holographic Centerpiece when conversation is clean */}
          {messages.length <= 1 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9, rotateX: 15 }}
              animate={{ opacity: 1, scale: 1, rotateX: 0 }}
              transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
              className="py-4 sm:py-6 flex flex-col items-center justify-center text-center space-y-3 preserve-3d"
            >
              {/* 3D Levitating Neural Sphere + Orbiting Telemetry Satellites */}
              <div className="relative flex items-center justify-center">
                <motion.div
                  animate={{
                    y: [0, -9, 0],
                    rotateZ: [0, 3, -3, 0]
                  }}
                  transition={{
                    duration: 4.5,
                    repeat: Infinity,
                    ease: 'easeInOut'
                  }}
                  className="relative p-2 rounded-full bg-gradient-to-tr from-cyan-500/15 via-transparent to-purple-500/15 border border-cyan-400/30 shadow-[0_0_45px_rgba(0,240,255,0.25)]"
                >
                  <MiniNeuralOrb3D
                    size={96}
                    active={
                      isStreaming ||
                      voiceState !== 'idle' ||
                      wakeWordStatus === 'capturing'
                    }
                    colorMode={voiceState === 'speaking' ? 'purple' : 'cyan'}
                  />
                </motion.div>

                {/* Orbiting 3D Badge Left */}
                <motion.div
                  animate={{ y: [0, 6, 0], x: [0, -4, 0] }}
                  transition={{ duration: 3.4, repeat: Infinity, ease: 'easeInOut' }}
                  className="hidden sm:flex items-center gap-1 px-2.5 py-1 rounded-full bg-black/70 border border-cyan-400/40 text-[10px] font-mono text-cyan-300 shadow-[0_0_15px_rgba(0,240,255,0.2)] absolute -left-28 top-3"
                >
                  <Database size={10} />
                  <span>1M Context</span>
                </motion.div>

                {/* Orbiting 3D Badge Right */}
                <motion.div
                  animate={{ y: [0, -6, 0], x: [0, 4, 0] }}
                  transition={{ duration: 3.8, repeat: Infinity, ease: 'easeInOut' }}
                  className="hidden sm:flex items-center gap-1 px-2.5 py-1 rounded-full bg-black/70 border border-amber-400/40 text-[10px] font-mono text-amber-300 shadow-[0_0_15px_rgba(251,191,36,0.2)] absolute -right-28 bottom-3"
                >
                  <Zap size={10} />
                  <span>385 TPS Turbo</span>
                </motion.div>
              </div>

              <motion.h1
                animate={{
                  textShadow: [
                    '0 0 12px rgba(0,240,255,0.35)',
                    '0 0 26px rgba(0,240,255,0.7)',
                    '0 0 12px rgba(0,240,255,0.35)'
                  ]
                }}
                transition={{ duration: 3.5, repeat: Infinity }}
                className="text-xl sm:text-2xl font-extrabold tracking-tight text-white"
              >
                Aura Assistant <span className="text-cyan-400">v3.5</span>
              </motion.h1>

              <p className="text-xs sm:text-sm text-white/55 max-w-lg leading-relaxed">
                Sovereign local AI workspace running 100% locally on your machine with Hybrid RRF Context &amp; NVIDIA Nemotron 3 Ultra support.
                {wakeWordEnabled && (
                  <span className="text-emerald-400 block mt-1 font-mono text-xs">
                    ✨ Hands-Free Mode Active: Just say &quot;Hey Aura&quot; to speak!
                  </span>
                )}
              </p>
            </motion.div>
          )}

          {/* 3D Animated & Cursor-Tilted Messages */}
          {messages.map((m, idx) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 22, rotateX: -14, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, rotateX: 0, scale: 1 }}
              transition={{
                type: 'spring',
                stiffness: 260,
                damping: 22,
                delay: Math.min(0.15, idx * 0.03)
              }}
              className={`flex flex-col preserve-3d ${
                m.sender === 'aura' ? 'items-start' : 'items-end'
              }`}
            >
              <Tilt3DCard
                intensity={5}
                glareColor={
                  m.sender === 'aura'
                    ? 'rgba(0, 240, 255, 0.12)'
                    : 'rgba(168, 85, 247, 0.16)'
                }
                className={`max-w-[92%] sm:max-w-[85%] rounded-2xl p-4 sm:p-5 text-sm leading-relaxed ${
                  m.sender === 'aura'
                    ? 'aura-msg-ai-3d text-[#E8E8F4]'
                    : 'aura-msg-user-3d text-cyan-50'
                }`}
              >
                {/* Message Header */}
                <div className="flex items-center justify-between gap-4 mb-2 pb-2 border-b border-white/[0.08]">
                  <div className="flex items-center gap-2 flex-wrap">
                    {m.sender === 'aura' ? (
                      <div className="flex items-center gap-1.5 text-cyan-300 font-bold text-xs aura-text-glow-cyan">
                        <Sparkles size={13} className="text-cyan-400 animate-pulse" />
                        <span>aura.</span>
                      </div>
                    ) : (
                      <span className="text-cyan-200 font-bold text-xs tracking-wide">
                        user
                      </span>
                    )}
                    <span className="text-[10px] text-white/35 font-mono">{m.timestamp}</span>

                    {m.sender === 'aura' && m.modelUsed && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-400/25 text-cyan-300">
                        {m.modelUsed}
                      </span>
                    )}

                    {m.sender === 'aura' && m.tps && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-400/25 text-amber-300 flex items-center gap-1">
                        <Zap size={9} />
                        {m.tps.toFixed(1)} TPS
                      </span>
                    )}
                  </div>

                  {/* Actions: Listen / Copy */}
                  {m.sender === 'aura' && (
                    <div className="flex items-center gap-1 relative z-30">
                      <motion.button
                        type="button"
                        whileHover={{ scale: 1.15, rotateZ: 6 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => speakText(m.text)}
                        title="Listen with pleasant girl voice"
                        className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-purple-500/20 text-white/50 hover:text-purple-300 transition-colors cursor-pointer"
                      >
                        <Volume2 size={13} />
                      </motion.button>
                      <motion.button
                        type="button"
                        whileHover={{ scale: 1.15, rotateZ: -6 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => handleCopy(m.id, m.text)}
                        title="Copy text"
                        className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-cyan-500/20 text-white/50 hover:text-cyan-300 transition-colors cursor-pointer"
                      >
                        {copiedId === m.id ? (
                          <Check size={13} className="text-green-400" />
                        ) : (
                          <Copy size={13} />
                        )}
                      </motion.button>
                    </div>
                  )}
                </div>

                {/* Message Content */}
                <div className="whitespace-pre-wrap font-sans text-sm sm:text-base leading-relaxed break-words relative z-10">
                  {m.text}
                </div>
              </Tilt3DCard>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Dynamic 3D Bottom Controls Dock */}
      <div className="relative z-10 p-3 sm:p-4 bg-gradient-to-t from-[#06070D] via-[#06070D]/95 to-transparent border-t border-white/[0.08] shrink-0 preserve-3d">
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-2.5 preserve-3d">
          {/* Progress Telemetry Banner */}
          <AnimatePresence>
            {isStreaming && (
              <motion.div
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.96 }}
                className="py-2 px-4 rounded-xl bg-cyan-500/15 border border-cyan-400/35 flex items-center justify-between text-xs text-cyan-200 shadow-[0_0_20px_rgba(0,240,255,0.2)]"
              >
                <div className="flex items-center gap-2.5">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                  </span>
                  <span className="font-mono">
                    Aura is generating response ({elapsedSec}s) • {dynamicTps.toFixed(1)} tok/s
                  </span>
                </div>
                <motion.button
                  type="button"
                  whileHover={{ scale: 1.06 }}
                  whileTap={{ scale: 0.94 }}
                  onClick={handleStop}
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-white/[0.12] hover:bg-white/[0.2] text-white transition-colors cursor-pointer"
                >
                  <Square size={10} className="fill-current" />
                  <span>Stop</span>
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* 3D Floating & Spring-Animated Prompt Chips */}
          {!isStreaming && (
            <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1 preserve-3d">
              {promptChips.map((chip, idx) => (
                <motion.button
                  key={chip.label}
                  type="button"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{
                    opacity: 1,
                    y: [0, -2.5, 0]
                  }}
                  transition={{
                    opacity: { duration: 0.3, delay: idx * 0.06 },
                    y: {
                      duration: 3.2 + idx * 0.4,
                      repeat: Infinity,
                      ease: 'easeInOut'
                    }
                  }}
                  whileHover={{
                    scale: 1.07,
                    y: -5,
                    rotateX: 10,
                    rotateY: idx % 2 === 0 ? 4 : -4
                  }}
                  whileTap={{ scale: 0.94 }}
                  onClick={() => handleChipClick(chip.prompt)}
                  className="aura-btn-3d shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-white/70 hover:text-cyan-300 hover:border-cyan-400/50 hover:bg-cyan-500/15 transition-colors text-xs cursor-pointer"
                >
                  {chip.label}
                </motion.button>
              ))}
            </div>
          )}

          {/* Interactive 3D Input Dock */}
          <motion.form
            onSubmit={handleSend}
            whileHover={{ scale: 1.004 }}
            className="aura-card-3d flex items-center gap-2 rounded-2xl p-1.5 sm:p-2 focus-within:border-cyan-400/65 focus-within:shadow-[0_0_28px_rgba(0,240,255,0.22)] transition-all"
          >
            {/* Microphone Button (Manual / Hands-free) */}
            <motion.button
              type="button"
              onClick={triggerManualVoice}
              whileHover={{ scale: 1.1, rotateZ: 6 }}
              whileTap={{ scale: 0.9 }}
              title={
                isMicActive ? 'Stop listening' : "Click to speak or say 'Hey Aura'"
              }
              className={`p-2.5 sm:p-3 rounded-xl transition-all cursor-pointer flex items-center justify-center shrink-0 ${
                isMicActive || voiceState === 'listening'
                  ? 'bg-cyan-400 text-black shadow-[0_0_24px_#00F0FF] animate-pulse'
                  : voiceState === 'speaking'
                  ? 'bg-purple-500 text-white shadow-[0_0_24px_#A855F7]'
                  : 'bg-white/[0.07] text-white/75 hover:text-cyan-300 hover:bg-white/[0.12]'
              }`}
            >
              <Mic size={18} />
            </motion.button>

            {/* Main Text Input */}
            <input
              type="text"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Ask Aura, type instructions, or say 'Hey Aura'..."
              disabled={isStreaming}
              className="flex-1 bg-transparent px-2 sm:px-3 py-2 text-sm sm:text-base text-white placeholder-white/35 focus:outline-none disabled:opacity-50 min-w-0"
            />

            {/* Voice-Back Chat Policy Toggle */}
            <motion.button
              type="button"
              whileHover={{ scale: 1.06, y: -1 }}
              whileTap={{ scale: 0.94 }}
              onClick={() => setIsAutoSpeakChat(!isAutoSpeakChat)}
              title={`Voice reply for typed chat is ${
                isAutoSpeakChat
                  ? 'ON'
                  : 'OFF (Voice reply active only for voice queries)'
              }`}
              className={`p-2 rounded-xl text-xs transition-all cursor-pointer hidden md:flex items-center gap-1.5 shrink-0 ${
                isAutoSpeakChat
                  ? 'bg-purple-500/25 border border-purple-400/45 text-purple-200'
                  : 'bg-white/[0.04] border border-white/[0.08] text-white/45 hover:text-white/75'
              }`}
            >
              <Volume2 size={14} />
              <span className="font-mono text-[10px]">
                {isAutoSpeakChat ? 'Voice: ON' : 'Voice: OFF'}
              </span>
            </motion.button>

            {/* Send / In Progress Button */}
            {isStreaming ? (
              <motion.button
                type="button"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleStop}
                title="Prompt in progress (Click to cancel)"
                className="px-4 py-2.5 sm:py-3 bg-amber-400/20 border border-amber-400/45 text-amber-300 font-semibold rounded-xl text-xs flex items-center gap-2 animate-pulse hover:bg-amber-400/30 transition-all cursor-pointer shrink-0 shadow-[0_0_15px_rgba(251,191,36,0.2)]"
              >
                <Loader2 size={15} className="animate-spin text-amber-400" />
                <span className="hidden sm:inline">In Progress...</span>
              </motion.button>
            ) : (
              <motion.button
                type="submit"
                whileHover={{ scale: 1.08, y: -2, rotateX: 8 }}
                whileTap={{ scale: 0.92 }}
                disabled={!inputVal.trim()}
                className="p-2.5 sm:px-5 sm:py-3 bg-gradient-to-r from-cyan-400 to-cyan-300 text-black font-bold rounded-xl text-sm hover:opacity-95 disabled:opacity-40 transition-all flex items-center justify-center cursor-pointer shrink-0 shadow-[0_0_20px_rgba(0,240,255,0.3)]"
              >
                <Send size={16} />
              </motion.button>
            )}
          </motion.form>
        </div>
      </div>
    </div>
  );
};

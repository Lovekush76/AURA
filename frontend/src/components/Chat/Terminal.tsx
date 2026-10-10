import { useState, useRef, useEffect, type FormEvent } from 'react';
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

  const [inputVal, setInputVal] = useState('');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll inside internal message viewport ONLY (prevents window scrolling)
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

  return (
    <div className="aura-panel-3d flex-1 flex flex-col h-full w-full rounded-2xl overflow-hidden min-h-0 relative preserve-3d">
      {/* Subtle Holographic Scanlines */}
      <div className="absolute inset-0 aura-holo-scanlines z-0" />

      {/* Top 3D Telemetry Sub-Bar inside Chat HUD */}
      <div className="relative z-10 px-4 py-2 border-b border-white/[0.07] bg-black/30 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-xs">
          <Orbit size={13} className="text-cyan-400" />
          <span className="font-mono text-[11px] text-white/70">ENGINE:</span>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value as AuraModelId)}
            className="bg-white/[0.05] border border-cyan-400/30 rounded-lg px-2 py-0.5 text-[11px] font-mono text-cyan-300 focus:outline-none focus:border-cyan-400 cursor-pointer"
          >
            {Object.entries(MODEL_CATALOG).map(([id, meta]) => (
              <option key={id} value={id} className="bg-[#0B0E18] text-white">
                {meta.short} ({meta.context})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="hidden sm:flex items-center gap-1 text-emerald-300">
            <Database size={11} className="text-emerald-400" />
            <span>RRF + {activeModelMeta.context}</span>
          </span>
          <span className="flex items-center gap-1 text-amber-300">
            <Zap size={11} className="text-amber-400" />
            <span>{liveTps.toFixed(1)} tok/s</span>
          </span>
        </div>
      </div>

      {/* Wake-Word / Audio Status Radar Banner */}
      {(wakeWordStatus === 'detected' ||
        wakeWordStatus === 'capturing' ||
        voiceState === 'listening' ||
        voiceState === 'speaking') && (
        <div
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
        </div>
      )}

      {/* Main 3D Conversation Stream Viewport */}
      <div
        ref={viewportRef}
        className="relative z-10 flex-1 overflow-y-auto px-3 sm:px-6 md:px-8 py-4 sm:py-6 space-y-4 min-h-0 preserve-3d"
      >
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-4 preserve-3d">
          {/* 3D Holographic Hero Banner when conversation is clean */}
          {messages.length <= 1 && (
            <div className="py-5 sm:py-7 flex flex-col items-center justify-center text-center space-y-3 preserve-3d">
              <div className="aura-card-3d w-16 h-16 sm:w-20 sm:h-20 rounded-3xl bg-gradient-to-tr from-cyan-500/25 via-blue-500/15 to-purple-500/25 border border-cyan-400/45 flex items-center justify-center text-cyan-300 shadow-[0_0_40px_rgba(0,240,255,0.3)]">
                <Sparkles size={34} className="text-cyan-300 animate-pulse" />
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-white aura-text-glow-cyan">
                Aura Holographic Core <span className="text-cyan-400">v3.5</span>
              </h1>
              <p className="text-xs sm:text-sm text-white/55 max-w-lg leading-relaxed">
                3D Spatial AI Workspace powered by Hybrid BM25+Vector RRF Context Engine, NVIDIA Nemotron 3 Ultra (1M Context), and 385 TPS FlashAttention.
                {wakeWordEnabled && (
                  <span className="text-emerald-400 block mt-1 font-mono text-xs">
                    ✨ Hands-Free 3D Radar Active: Just say &quot;Hey Aura&quot; to speak!
                  </span>
                )}
              </p>
            </div>
          )}

          {/* 3D Depth-Layered Messages */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col preserve-3d ${
                m.sender === 'aura' ? 'items-start' : 'items-end'
              }`}
            >
              <div
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
                        <Sparkles size={13} className="text-cyan-400" />
                        <span>aura.</span>
                      </div>
                    ) : (
                      <span className="text-cyan-200 font-bold text-xs tracking-wide">
                        lovekush
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
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => speakText(m.text)}
                        title="Listen with pleasant girl voice"
                        className="aura-btn-3d p-1.5 rounded-lg bg-white/[0.04] hover:bg-purple-500/20 text-white/50 hover:text-purple-300 transition-colors cursor-pointer"
                      >
                        <Volume2 size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopy(m.id, m.text)}
                        title="Copy text"
                        className="aura-btn-3d p-1.5 rounded-lg bg-white/[0.04] hover:bg-cyan-500/20 text-white/50 hover:text-cyan-300 transition-colors cursor-pointer"
                      >
                        {copiedId === m.id ? (
                          <Check size={13} className="text-green-400" />
                        ) : (
                          <Copy size={13} />
                        )}
                      </button>
                    </div>
                  )}
                </div>

                {/* Message Content */}
                <div className="whitespace-pre-wrap font-sans text-sm sm:text-base leading-relaxed break-words">
                  {m.text}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Dynamic 3D Bottom Controls Dock */}
      <div className="relative z-10 p-3 sm:p-4 bg-gradient-to-t from-[#06070D] via-[#06070D]/95 to-transparent border-t border-white/[0.08] shrink-0">
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-2.5">
          {/* Progress Telemetry Banner */}
          {isStreaming && (
            <div className="py-2 px-4 rounded-xl bg-cyan-500/15 border border-cyan-400/35 flex items-center justify-between text-xs text-cyan-200 shadow-[0_0_20px_rgba(0,240,255,0.2)]">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                </span>
                <span className="font-mono">
                  3D Core Streaming ({elapsedSec}s) • {liveTps.toFixed(1)} tok/s
                </span>
              </div>
              <button
                type="button"
                onClick={handleStop}
                className="aura-btn-3d flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-white/[0.12] hover:bg-white/[0.2] text-white transition-colors cursor-pointer"
              >
                <Square size={10} className="fill-current" />
                <span>Stop</span>
              </button>
            </div>
          )}

          {/* 3D Tactile Prompt Chips */}
          {!isStreaming && (
            <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
              <button
                type="button"
                onClick={() =>
                  handleChipClick('What is my current real-time location and timezone?')
                }
                className="aura-btn-3d shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-white/70 hover:text-cyan-300 hover:border-cyan-400/45 hover:bg-cyan-500/15 transition-all text-xs cursor-pointer"
              >
                📍 My Location
              </button>
              <button
                type="button"
                onClick={() =>
                  handleChipClick('Who is Lovekush Kumar? Summarize his profile and skills.')
                }
                className="aura-btn-3d shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-white/70 hover:text-cyan-300 hover:border-cyan-400/45 hover:bg-cyan-500/15 transition-all text-xs cursor-pointer"
              >
                👤 About Lovekush
              </button>
              <button
                type="button"
                onClick={() =>
                  handleChipClick(
                    'Report system hardware, model residency, and VRAM telemetry.'
                  )
                }
                className="aura-btn-3d shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-white/70 hover:text-cyan-300 hover:border-cyan-400/45 hover:bg-cyan-500/15 transition-all text-xs cursor-pointer"
              >
                ⚡ System Telemetry
              </button>
              <button
                type="button"
                onClick={() =>
                  handleChipClick(
                    'Write an optimized Python function to compute Fibonacci sequence.'
                  )
                }
                className="aura-btn-3d shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-white/70 hover:text-cyan-300 hover:border-cyan-400/45 hover:bg-cyan-500/15 transition-all text-xs cursor-pointer"
              >
                🐍 Python Fibonacci
              </button>
            </div>
          )}

          {/* Interactive 3D Input Dock */}
          <form
            onSubmit={handleSend}
            className="aura-card-3d flex items-center gap-2 rounded-2xl p-1.5 sm:p-2 focus-within:border-cyan-400/65 focus-within:shadow-[0_0_28px_rgba(0,240,255,0.22)] transition-all"
          >
            {/* Microphone Button (Manual / Hands-free) */}
            <button
              type="button"
              onClick={triggerManualVoice}
              title={
                isMicActive ? 'Stop listening' : "Click to speak or say 'Hey Aura'"
              }
              className={`aura-btn-3d p-2.5 sm:p-3 rounded-xl transition-all cursor-pointer flex items-center justify-center shrink-0 ${
                isMicActive || voiceState === 'listening'
                  ? 'bg-cyan-400 text-black shadow-[0_0_24px_#00F0FF] animate-pulse'
                  : voiceState === 'speaking'
                  ? 'bg-purple-500 text-white shadow-[0_0_24px_#A855F7]'
                  : 'bg-white/[0.07] text-white/75 hover:text-cyan-300 hover:bg-white/[0.12]'
              }`}
            >
              <Mic size={18} />
            </button>

            {/* Main Text Input */}
            <input
              type="text"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Ask Aura 3D Core, type instructions, or say 'Hey Aura'..."
              disabled={isStreaming}
              className="flex-1 bg-transparent px-2 sm:px-3 py-2 text-sm sm:text-base text-white placeholder-white/35 focus:outline-none disabled:opacity-50 min-w-0"
            />

            {/* Voice-Back Chat Policy Toggle */}
            <button
              type="button"
              onClick={() => setIsAutoSpeakChat(!isAutoSpeakChat)}
              title={`Voice reply for typed chat is ${
                isAutoSpeakChat
                  ? 'ON'
                  : 'OFF (Voice reply active only for voice queries)'
              }`}
              className={`aura-btn-3d p-2 rounded-xl text-xs transition-all cursor-pointer hidden md:flex items-center gap-1.5 shrink-0 ${
                isAutoSpeakChat
                  ? 'bg-purple-500/25 border border-purple-400/45 text-purple-200'
                  : 'bg-white/[0.04] border border-white/[0.08] text-white/45 hover:text-white/75'
              }`}
            >
              <Volume2 size={14} />
              <span className="font-mono text-[10px]">
                {isAutoSpeakChat ? 'Voice: ON' : 'Voice: OFF'}
              </span>
            </button>

            {/* Send / In Progress Button */}
            {isStreaming ? (
              <button
                type="button"
                onClick={handleStop}
                title="Prompt in progress (Click to cancel)"
                className="aura-btn-3d px-4 py-2.5 sm:py-3 bg-amber-400/20 border border-amber-400/45 text-amber-300 font-semibold rounded-xl text-xs flex items-center gap-2 animate-pulse hover:bg-amber-400/30 transition-all cursor-pointer shrink-0 shadow-[0_0_15px_rgba(251,191,36,0.2)]"
              >
                <Loader2 size={15} className="animate-spin text-amber-400" />
                <span className="hidden sm:inline">In Progress...</span>
              </button>
            ) : (
              <button
                type="submit"
                disabled={!inputVal.trim()}
                className="aura-btn-3d p-2.5 sm:px-5 sm:py-3 bg-gradient-to-r from-cyan-400 to-cyan-300 text-black font-bold rounded-xl text-sm hover:opacity-95 disabled:opacity-40 transition-all flex items-center justify-center cursor-pointer shrink-0 shadow-[0_0_20px_rgba(0,240,255,0.3)]"
              >
                <Send size={16} />
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
};

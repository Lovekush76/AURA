import { useState, useRef, useEffect, type FormEvent } from 'react';
import { Send, Loader2, Square, Sparkles, Volume2, Mic, Copy, Check, Radio } from 'lucide-react';
import { useChatStore } from '../../store/chatStore';
import { useLocationStore } from '../../store/locationStore';
import { useVoiceStore } from '../../store/voiceStore';
import { useWakeWord } from '../../hooks/useWakeWord';

export const Terminal = () => {
  const { messages, isStreaming, addMessage, appendStreamChunk, setStreaming } = useChatStore();
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

    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer aura_sec_default_change_me'
        },
        body: JSON.stringify({
          prompt: queryText,
          channel: 'text', // Typed query
          location: location
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
                  appendStreamChunk(data.content);
                  fullResponse += data.content;
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
                appendStreamChunk(data.content);
                fullResponse += data.content;
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

  return (
    <div className="flex-1 flex flex-col h-full w-full bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl min-h-0 relative">
      {/* Wake-Word / Audio Status Radar Banner */}
      {(wakeWordStatus === 'detected' || wakeWordStatus === 'capturing' || voiceState === 'listening' || voiceState === 'speaking') && (
        <div className={`px-4 py-2 border-b flex items-center justify-between text-xs transition-all z-20 ${
          wakeWordStatus === 'detected'
            ? 'bg-amber-500/15 border-amber-400/30 text-amber-300 animate-pulse'
            : wakeWordStatus === 'capturing' || voiceState === 'listening'
            ? 'bg-cyan-500/15 border-cyan-400/30 text-cyan-300 shadow-[0_0_20px_rgba(0,240,255,0.2)]'
            : 'bg-purple-500/15 border-purple-400/30 text-purple-300'
        }`}>
          <div className="flex items-center gap-2.5">
            <Radio size={14} className="animate-spin text-cyan-400" />
            <span className="font-semibold">{wakeWordMessage}</span>
          </div>
          <span className="text-[11px] font-mono opacity-70">
            {voiceState === 'speaking' ? `Aura Voice: ${selectedVoiceName.split(' ')[1] || 'Pleasant'}` : 'Hands-Free Radar Active'}
          </span>
        </div>
      )}

      {/* Main Conversation Stream Viewport (Dynamic Fluid Height) */}
      <div ref={viewportRef} className="flex-1 overflow-y-auto px-3 sm:px-6 md:px-8 py-4 sm:py-6 space-y-4 min-h-0">
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-4">
          {/* Welcome Banner when conversation is clean */}
          {messages.length <= 1 && (
            <div className="py-8 sm:py-12 flex flex-col items-center justify-center text-center space-y-3">
              <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-3xl bg-gradient-to-tr from-cyan-500/20 to-purple-500/20 border border-cyan-400/30 flex items-center justify-center text-cyan-300 shadow-[0_0_30px_rgba(0,240,255,0.2)]">
                <Sparkles size={36} className="text-cyan-400" />
              </div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
                Aura Assistant <span className="text-cyan-400">v3.5</span>
              </h1>
              <p className="text-xs sm:text-sm text-white/50 max-w-lg leading-relaxed">
                Sovereign local AI workspace running 100% locally on your machine.
                {wakeWordEnabled && <span className="text-emerald-400 block mt-1 font-mono text-xs">✨ Hands-Free Mode Active: Just say "Hey Aura" to speak!</span>}
              </p>
            </div>
          )}

          {/* Messages */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${
                m.sender === 'aura' ? 'items-start' : 'items-end'
              }`}
            >
              <div
                className={`max-w-[90%] sm:max-w-[85%] rounded-2xl p-4 sm:p-5 border transition-all text-sm leading-relaxed ${
                  m.sender === 'aura'
                    ? 'bg-white/[0.04] border-white/[0.08] text-[#E0E0EC] shadow-[0_4px_20px_rgba(0,0,0,0.2)]'
                    : 'bg-cyan-500/15 border-cyan-400/30 text-cyan-100 shadow-[0_0_20px_rgba(0,240,255,0.1)]'
                }`}
              >
                {/* Message Header */}
                <div className="flex items-center justify-between gap-4 mb-2 pb-2 border-b border-white/[0.06]">
                  <div className="flex items-center gap-2">
                    {m.sender === 'aura' ? (
                      <div className="flex items-center gap-1.5 text-cyan-400 font-semibold text-xs">
                        <Sparkles size={13} />
                        <span>aura.</span>
                      </div>
                    ) : (
                      <span className="text-cyan-300 font-semibold text-xs">user</span>
                    )}
                    <span className="text-[10px] text-white/30 font-mono">{m.timestamp}</span>
                  </div>

                  {/* Actions: Listen / Copy */}
                  {m.sender === 'aura' && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => speakText(m.text)}
                        title="Listen with pleasant girl voice"
                        className="p-1 rounded-lg hover:bg-white/10 text-white/40 hover:text-purple-300 transition-colors cursor-pointer"
                      >
                        <Volume2 size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopy(m.id, m.text)}
                        title="Copy text"
                        className="p-1 rounded-lg hover:bg-white/10 text-white/40 hover:text-cyan-300 transition-colors cursor-pointer"
                      >
                        {copiedId === m.id ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
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

      {/* Dynamic Bottom Controls Dock */}
      <div className="p-3 sm:p-5 bg-gradient-to-t from-[#08080C] via-[#08080C]/90 to-transparent border-t border-white/[0.06] shrink-0">
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-2.5">
          {/* Progress Telemetry Banner */}
          {isStreaming && (
            <div className="py-2 px-4 rounded-xl bg-cyan-500/10 border border-cyan-400/25 flex items-center justify-between text-xs text-cyan-300 animate-pulse">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                </span>
                <span className="font-mono">Aura is generating response ({elapsedSec}s)</span>
              </div>
              <button
                type="button"
                onClick={handleStop}
                className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-white/[0.1] hover:bg-white/[0.2] text-white transition-colors cursor-pointer"
              >
                <Square size={10} className="fill-current" />
                <span>Stop</span>
              </button>
            </div>
          )}

          {/* Prompt Chips */}
          {!isStreaming && (
            <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
              <button
                type="button"
                onClick={() => handleChipClick("What is my current real-time location and timezone?")}
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
              >
                📍 My Location
              </button>
              <button
                type="button"
                onClick={() => handleChipClick("Who is Lovekush Kumar? Summarize his profile and skills.")}
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
              >
                👤 About Lovekush
              </button>
              <button
                type="button"
                onClick={() => handleChipClick("Report system hardware, model residency, and VRAM telemetry.")}
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
              >
                ⚡ System Telemetry
              </button>
              <button
                type="button"
                onClick={() => handleChipClick("Write an optimized Python function to compute Fibonacci sequence.")}
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
              >
                🐍 Python Fibonacci
              </button>
            </div>
          )}

          {/* Interactive Input Dock */}
          <form onSubmit={handleSend} className="flex items-center gap-2 bg-white/[0.04] border border-white/[0.1] rounded-2xl p-1.5 sm:p-2 focus-within:border-cyan-400/60 focus-within:shadow-[0_0_20px_rgba(0,240,255,0.15)] transition-all">
            {/* Microphone Button (Manual / Hands-free) */}
            <button
              type="button"
              onClick={triggerManualVoice}
              title={isMicActive ? "Stop listening" : "Click to speak or say 'Hey Aura'"}
              className={`p-2.5 sm:p-3 rounded-xl transition-all cursor-pointer flex items-center justify-center shrink-0 ${
                isMicActive || voiceState === 'listening'
                  ? 'bg-cyan-400 text-black shadow-[0_0_20px_#00F0FF] animate-pulse'
                  : voiceState === 'speaking'
                  ? 'bg-purple-500 text-white shadow-[0_0_20px_#A855F7]'
                  : 'bg-white/[0.06] text-white/70 hover:text-cyan-300 hover:bg-white/[0.1]'
              }`}
            >
              <Mic size={18} />
            </button>

            {/* Main Text Input */}
            <input
              type="text"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Ask Aura, type instructions, or say 'Hey Aura'..."
              disabled={isStreaming}
              className="flex-1 bg-transparent px-2 sm:px-3 py-2 text-sm sm:text-base text-white placeholder-white/30 focus:outline-none disabled:opacity-50 min-w-0"
            />

            {/* Voice-Back Chat Policy Toggle */}
            <button
              type="button"
              onClick={() => setIsAutoSpeakChat(!isAutoSpeakChat)}
              title={`Voice reply for typed chat is ${isAutoSpeakChat ? 'ON' : 'OFF (Voice reply active only for voice queries)'}`}
              className={`p-2 rounded-xl text-xs transition-all cursor-pointer hidden md:flex items-center gap-1.5 shrink-0 ${
                isAutoSpeakChat
                  ? 'bg-purple-500/20 border border-purple-400/40 text-purple-300'
                  : 'bg-white/[0.03] border border-white/[0.06] text-white/40 hover:text-white/70'
              }`}
            >
              <Volume2 size={14} />
              <span className="font-mono text-[10px]">{isAutoSpeakChat ? 'Voice: ON' : 'Voice: OFF'}</span>
            </button>

            {/* Send / In Progress Button */}
            {isStreaming ? (
              <button
                type="button"
                onClick={handleStop}
                title="Prompt in progress (Click to cancel)"
                className="px-4 py-2.5 sm:py-3 bg-amber-400/20 border border-amber-400/40 text-amber-300 font-semibold rounded-xl text-xs flex items-center gap-2 animate-pulse hover:bg-amber-400/30 transition-all cursor-pointer shrink-0 shadow-[0_0_15px_rgba(251,191,36,0.2)]"
              >
                <Loader2 size={15} className="animate-spin text-amber-400" />
                <span className="hidden sm:inline">In Progress...</span>
              </button>
            ) : (
              <button
                type="submit"
                disabled={!inputVal.trim()}
                className="p-2.5 sm:px-5 sm:py-3 bg-cyan-400 text-black font-semibold rounded-xl text-sm hover:bg-cyan-300 disabled:opacity-40 transition-colors flex items-center justify-center cursor-pointer shrink-0 shadow-[0_0_15px_rgba(0,240,255,0.2)]"
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

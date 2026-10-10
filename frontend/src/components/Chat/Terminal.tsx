import { memo, useState, useRef, useEffect, useCallback, type FormEvent } from 'react';
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
  Database,
  Cpu,
  ArrowDown
} from 'lucide-react';
import {
  useChatStore,
  MODEL_CATALOG,
  type AuraModelId,
  type ChatMessage
} from '../../store/chatStore';
import { useLocationStore } from '../../store/locationStore';
import { useVoiceStore } from '../../store/voiceStore';
import { useWakeWord } from '../../hooks/useWakeWord';
import { getAuthHeaders, getAuraSessionId } from '../../config/api';
import { consumeAuraSseStream } from '../../utils/sseStream';

const AUTO_SCROLL_THRESHOLD_PX = 80;

interface MessageRowProps {
  message: ChatMessage;
  isCopied: boolean;
  onCopy: (id: string, text: string) => void;
  onSpeak: (text: string) => void;
}

const MessageRow = memo(({ message: m, isCopied, onCopy, onSpeak }: MessageRowProps) => {
  return (
    <div
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
        <div className="flex items-center justify-between gap-4 mb-2 pb-2 border-b border-white/[0.06]">
          <div className="flex items-center gap-2 flex-wrap">
            {m.sender === 'aura' ? (
              <div className="flex items-center gap-1.5 text-cyan-400 font-semibold text-xs">
                <Sparkles size={13} />
                <span>aura.</span>
              </div>
            ) : (
              <span className="text-cyan-300 font-semibold text-xs">user</span>
            )}
            <span className="text-[10px] text-white/30 font-mono">{m.timestamp}</span>

            {m.sender === 'aura' && m.modelUsed && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-400/20 text-cyan-300">
                {m.modelUsed}
              </span>
            )}

            {m.sender === 'aura' && m.tps && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-400/20 text-amber-300 flex items-center gap-1">
                <Zap size={9} />
                {m.tps.toFixed(1)} TPS
              </span>
            )}
          </div>

          {m.sender === 'aura' && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onSpeak(m.text)}
                title="Listen with pleasant voice"
                className="p-1 rounded-lg hover:bg-white/10 text-white/40 hover:text-purple-300 transition-colors cursor-pointer"
              >
                <Volume2 size={13} />
              </button>
              <button
                type="button"
                onClick={() => onCopy(m.id, m.text)}
                title="Copy text"
                className="p-1 rounded-lg hover:bg-white/10 text-white/40 hover:text-cyan-300 transition-colors cursor-pointer"
              >
                {isCopied ? (
                  <Check size={13} className="text-green-400" />
                ) : (
                  <Copy size={13} />
                )}
              </button>
            </div>
          )}
        </div>

        <div className="whitespace-pre-wrap font-sans text-sm sm:text-base leading-relaxed break-words">
          {m.text}
        </div>
      </div>
    </div>
  );
});

MessageRow.displayName = 'MessageRow';

export const Terminal = () => {
  // Granular store selectors
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const selectedModel = useChatStore((s) => s.selectedModel);
  const activeRoutedModel = useChatStore((s) => s.activeRoutedModel);
  const setSelectedModel = useChatStore((s) => s.setSelectedModel);
  const setActiveRoutedModel = useChatStore((s) => s.setActiveRoutedModel);
  const liveTps = useChatStore((s) => s.liveTps);
  const peakTps = useChatStore((s) => s.peakTps);
  const addMessage = useChatStore((s) => s.addMessage);
  const appendStreamChunk = useChatStore((s) => s.appendStreamChunk);
  const setStreaming = useChatStore((s) => s.setStreaming);

  const location = useLocationStore((s) => s.location);

  const selectedVoiceName = useVoiceStore((s) => s.selectedVoiceName);
  const voiceState = useVoiceStore((s) => s.voiceState);
  const isMicActive = useVoiceStore((s) => s.isMicActive);
  const wakeWordStatus = useVoiceStore((s) => s.wakeWordStatus);
  const wakeWordMessage = useVoiceStore((s) => s.wakeWordMessage);
  const wakeWordEnabled = useVoiceStore((s) => s.wakeWordEnabled);
  const isAutoSpeakChat = useVoiceStore((s) => s.isAutoSpeakChat);
  const setIsAutoSpeakChat = useVoiceStore((s) => s.setIsAutoSpeakChat);
  const speakText = useVoiceStore((s) => s.speakText);

  const { triggerManualVoice } = useWakeWord();

  const [inputVal, setInputVal] = useState('');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef<boolean>(true);
  const scrollRafRef = useRef<number | null>(null);

  const handleViewportScroll = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX;
    isNearBottomRef.current = nearBottom;
    setIsUserScrolledUp(!nearBottom);
  }, []);

  const scrollToBottom = useCallback((force = false) => {
    if (!force && !isNearBottomRef.current) return;
    if (scrollRafRef.current !== null) return;
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null;
      const el = viewportRef.current;
      if (el && (force || isNearBottomRef.current)) {
        el.scrollTop = el.scrollHeight;
        isNearBottomRef.current = true;
        setIsUserScrolledUp(false);
      }
    });
  }, []);

  // Batched auto-scroll only when user is within 80px of bottom
  useEffect(() => {
    scrollToBottom(false);
  }, [messages, scrollToBottom]);

  useEffect(() => {
    return () => {
      if (scrollRafRef.current !== null) {
        cancelAnimationFrame(scrollRafRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

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

  const handleCopy = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  const handleSpeak = useCallback(
    (text: string) => {
      speakText(text);
    },
    [speakText]
  );

  const sendQuery = async (queryText: string) => {
    setActiveRoutedModel(null);
    addMessage('user', queryText);
    setStreaming(true);
    scrollToBottom(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          prompt: queryText,
          channel: 'text',
          location: location,
          session_id: getAuraSessionId(),
          override_model: selectedModel === 'auto' ? undefined : selectedModel
        }),
        signal: controller.signal
      });

      const fullResponse = await consumeAuraSseStream(
        response,
        {
          onRouting: (evt) => {
            setActiveRoutedModel(evt.model);
          },
          onTokenBatch: (batchText, measuredTps, routedModel) => {
            appendStreamChunk(batchText, measuredTps, routedModel);
          },
          onError: (errMsg) => {
            appendStreamChunk(`\n[Stream Error: ${errMsg}]`);
          }
        },
        controller.signal
      );

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
    <div className="flex-1 flex flex-col h-full w-full bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden backdrop-blur-xl min-h-0 relative">
      {/* Top Engine, Context Capacity & Speed Telemetry Bar */}
      <div className="px-4 py-2 border-b border-white/[0.06] bg-white/[0.02] flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-xs">
          <Cpu size={13} className="text-cyan-400" />
          <span className="font-mono text-[11px] text-white/60">ENGINE:</span>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value as AuraModelId)}
            className="bg-white/[0.05] border border-cyan-400/25 rounded-lg px-2.5 py-1 text-[11px] font-mono text-cyan-300 focus:outline-none focus:border-cyan-400 cursor-pointer"
          >
            {Object.entries(MODEL_CATALOG).map(([id, meta]) => (
              <option key={id} value={id} className="bg-[#0B0E18] text-white">
                {meta.label} ({meta.context})
              </option>
            ))}
          </select>
          {activeRoutedModel && (
            <span className="hidden md:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-400/30 text-cyan-300">
              Active: {activeRoutedModel}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2.5 text-[11px] font-mono flex-wrap">
          <span className="hidden sm:flex items-center gap-1 text-emerald-300 bg-emerald-500/10 border border-emerald-400/20 px-2 py-0.5 rounded-md">
            <Database size={11} className="text-emerald-400" />
            <span>RRF + {activeModelMeta.context}</span>
          </span>
          <span className="flex items-center gap-1 text-amber-300 bg-amber-500/10 border border-amber-400/20 px-2 py-0.5 rounded-md">
            <Zap size={11} className="text-amber-400" />
            <span>
              {liveTps.toFixed(1)} tok/s (Peak {peakTps.toFixed(1)})
            </span>
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

      {/* Main Conversation Stream Viewport */}
      <div
        ref={viewportRef}
        onScroll={handleViewportScroll}
        className="flex-1 overflow-y-auto px-3 sm:px-6 md:px-8 py-4 sm:py-6 space-y-4 min-h-0"
      >
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-4">
          {messages.length <= 1 && (
            <div className="py-6 sm:py-10 flex flex-col items-center justify-center text-center space-y-3">
              <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-3xl bg-gradient-to-tr from-cyan-500/20 to-purple-500/20 border border-cyan-400/30 flex items-center justify-center text-cyan-300 shadow-[0_0_30px_rgba(0,240,255,0.2)]">
                <Sparkles size={36} className="text-cyan-400" />
              </div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
                Aura Assistant <span className="text-cyan-400">v3.5</span>
              </h1>
              <p className="text-xs sm:text-sm text-white/50 max-w-lg leading-relaxed">
                Sovereign local AI workspace with Hybrid RRF Context, single-gate VRAM residency, and 60fps batched token streaming.
                {wakeWordEnabled && (
                  <span className="text-emerald-400 block mt-1 font-mono text-xs">
                    ✨ Hands-Free Mode Active: Just say &quot;Hey Aura&quot; to speak!
                  </span>
                )}
              </p>
            </div>
          )}

          {messages.map((m) => (
            <MessageRow
              key={m.id}
              message={m}
              isCopied={copiedId === m.id}
              onCopy={handleCopy}
              onSpeak={handleSpeak}
            />
          ))}
        </div>
      </div>

      {/* Floating Jump-to-Latest Button when User Scrolls Up */}
      {isUserScrolledUp && (
        <div className="absolute bottom-28 right-6 z-30">
          <button
            type="button"
            onClick={() => scrollToBottom(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-cyan-500/20 border border-cyan-400/40 text-cyan-200 text-xs font-mono shadow-lg backdrop-blur-md hover:bg-cyan-500/30 transition-all cursor-pointer"
          >
            <ArrowDown size={13} />
            <span>Jump to latest</span>
          </button>
        </div>
      )}

      {/* Dynamic Bottom Controls Dock */}
      <div className="p-3 sm:p-5 bg-gradient-to-t from-[#08080C] via-[#08080C]/90 to-transparent border-t border-white/[0.06] shrink-0">
        <div className="max-w-4xl xl:max-w-5xl mx-auto w-full space-y-2.5">
          {isStreaming && (
            <div className="py-2 px-4 rounded-xl bg-cyan-500/10 border border-cyan-400/25 flex items-center justify-between text-xs text-cyan-300 animate-pulse">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                </span>
                <span className="font-mono">
                  Aura is generating response ({elapsedSec}s) • {liveTps.toFixed(1)} tok/s
                </span>
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

          {!isStreaming && (
            <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
              <button
                type="button"
                onClick={() =>
                  handleChipClick('What is my current real-time location and timezone?')
                }
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
              >
                📍 My Location
              </button>
              <button
                type="button"
                onClick={() =>
                  handleChipClick('Who is Lovekush Kumar? Summarize his profile and skills.')
                }
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
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
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
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
                className="shrink-0 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/60 hover:text-cyan-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-all text-xs cursor-pointer"
              >
                🐍 Python Fibonacci
              </button>
            </div>
          )}

          <form
            onSubmit={handleSend}
            className="flex items-center gap-2 bg-white/[0.04] border border-white/[0.1] rounded-2xl p-1.5 sm:p-2 focus-within:border-cyan-400/60 focus-within:shadow-[0_0_20px_rgba(0,240,255,0.15)] transition-all"
          >
            <button
              type="button"
              onClick={triggerManualVoice}
              title={
                isMicActive ? 'Stop listening' : "Click to speak or say 'Hey Aura'"
              }
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

            <input
              type="text"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Ask Aura, type instructions, or say 'Hey Aura'..."
              disabled={isStreaming}
              className="flex-1 bg-transparent px-2 sm:px-3 py-2 text-sm sm:text-base text-white placeholder-white/30 focus:outline-none disabled:opacity-50 min-w-0"
            />

            <button
              type="button"
              onClick={() => setIsAutoSpeakChat(!isAutoSpeakChat)}
              title={`Voice reply for typed chat is ${
                isAutoSpeakChat
                  ? 'ON'
                  : 'OFF (Voice reply active only for voice queries)'
              }`}
              className={`p-2 rounded-xl text-xs transition-all cursor-pointer hidden md:flex items-center gap-1.5 shrink-0 ${
                isAutoSpeakChat
                  ? 'bg-purple-500/20 border border-purple-400/40 text-purple-300'
                  : 'bg-white/[0.03] border border-white/[0.06] text-white/40 hover:text-white/70'
              }`}
            >
              <Volume2 size={14} />
              <span className="font-mono text-[10px]">
                {isAutoSpeakChat ? 'Voice: ON' : 'Voice: OFF'}
              </span>
            </button>

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

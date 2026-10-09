import { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Mic, MicOff, Volume2 } from 'lucide-react';
import { useVoiceStore } from '../../store/voiceStore';
import { useChatStore } from '../../store/chatStore';
import { useLocationStore } from '../../store/locationStore';

export const Visualizer = () => {
  const {
    voiceState,
    audioAmplitude,
    isMicActive,
    selectedVoiceName,
    speechRate,
    speechPitch,
    initVoices,
    setVoiceState,
    setAudioAmplitude,
    setMicActive
  } = useVoiceStore();
  const { addMessage, appendStreamChunk, setStreaming } = useChatStore();
  const { location } = useLocationStore();
  const recognitionRef = useRef<any>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    initVoices();
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch {}
      }
      if (audioContextRef.current) {
        try { audioContextRef.current.close(); } catch {}
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [initVoices]);

  const speakText = (text: string) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    setVoiceState('speaking');

    // Clean markdown and code blocks for pleasant, natural voice articulation
    const cleanSpeech = text
      .replace(/```[\s\S]*?```/g, 'Code block omitted.')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/[*#_~]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .trim();

    const utterance = new SpeechSynthesisUtterance(cleanSpeech);

    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find(v => v.name === selectedVoiceName) ||
                  voices.find(v => v.name.toLowerCase().includes('zira')) ||
                  voices.find(v => v.name.toLowerCase().includes('heera')) ||
                  voices.find(v => v.name.toLowerCase().includes('female'));

    if (voice) {
      utterance.voice = voice;
    }
    utterance.rate = speechRate || 1.0;
    utterance.pitch = speechPitch || 1.08; // Pleasant female warmth

    utterance.onend = () => {
      setVoiceState('idle');
    };
    utterance.onerror = () => {
      setVoiceState('idle');
    };
    window.speechSynthesis.speak(utterance);
  };

  const handleSendVoiceQuery = async (queryText: string) => {
    addMessage('user', queryText);
    setStreaming(true);
    setVoiceState('transcribing');

    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer aura_sec_default_change_me'
        },
        body: JSON.stringify({ prompt: queryText, channel: 'voice', location: location })
      });

      if (!response.body) throw new Error('No response stream');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulatedText = '';

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
                  accumulatedText += data.content;
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
                accumulatedText += data.content;
              }
            } catch {}
          }
        }
      }

      if (accumulatedText.trim()) {
        speakText(accumulatedText.trim());
      } else {
        setVoiceState('idle');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      appendStreamChunk(`\n[Voice Error: ${msg}]`);
      setVoiceState('idle');
    } finally {
      setStreaming(false);
    }
  };

  const startVoiceInput = async () => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRec) {
      // Fallback voice simulation if browser does not support SpeechRecognition
      const fallbackPrompt = window.prompt("Voice recognition not supported in this browser. Enter voice command:", "Hey Aura, check system status");
      if (fallbackPrompt) {
        handleSendVoiceQuery(fallbackPrompt);
      }
      return;
    }

    try {
      const recognition = new SpeechRec();
      recognitionRef.current = recognition;
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setVoiceState('listening');
        setMicActive(true);
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          handleSendVoiceQuery(transcript);
        }
      };

      recognition.onerror = (e: any) => {
        console.warn('Speech recognition error:', e.error);
        setVoiceState('idle');
        setMicActive(false);
      };

      recognition.onend = () => {
        setMicActive(false);
        if (voiceState === 'listening') {
          setVoiceState('idle');
        }
      };

      // Try capturing real microphone stream to drive visualizer bars
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
          audioContextRef.current = audioCtx;
          const source = audioCtx.createMediaStreamSource(stream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 32;
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          const updateBars = () => {
            if (voiceState === 'listening' || voiceState === 'speaking') {
              analyser.getByteFrequencyData(dataArray);
              const amps = Array.from(dataArray.slice(0, 7)).map(v => Math.max(15, Math.min(100, v)));
              setAudioAmplitude(amps);
              animFrameRef.current = requestAnimationFrame(updateBars);
            }
          };
          updateBars();
        }).catch(() => {
          // Fallback animated amplitudes
        });
      }

      recognition.start();
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
      setVoiceState('idle');
      setMicActive(false);
    }
  };

  const stopVoiceInput = () => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setVoiceState('idle');
    setMicActive(false);
  };

  const toggleMic = () => {
    if (voiceState === 'listening' || voiceState === 'speaking') {
      stopVoiceInput();
    } else {
      startVoiceInput();
    }
  };

  return (
    <div className="h-32 bg-white/[0.03] border border-white/[0.08] rounded-2xl flex items-center justify-between p-6">
      <div className="flex items-center gap-4">
        <button
          onClick={toggleMic}
          type="button"
          title={voiceState === 'listening' ? "Click to stop listening" : "Click to speak to Aura"}
          className="relative group focus:outline-none"
        >
          <motion.div
            animate={{ scale: voiceState === 'listening' ? [1, 1.25, 1] : 1 }}
            transition={{ repeat: Infinity, duration: 1.2 }}
            className={`w-12 h-12 rounded-full flex items-center justify-center cursor-pointer transition-all ${
              voiceState === 'listening'
                ? 'bg-cyan-400 text-black shadow-[0_0_25px_#00F0FF]'
                : voiceState === 'speaking'
                ? 'bg-purple-500 text-white shadow-[0_0_25px_#A855F7]'
                : voiceState === 'transcribing'
                ? 'bg-amber-400 text-black animate-pulse'
                : 'bg-white/10 text-white hover:bg-cyan-500/20 hover:text-cyan-300'
            }`}
          >
            {voiceState === 'speaking' ? (
              <Volume2 size={22} />
            ) : voiceState === 'listening' ? (
              <Mic size={22} />
            ) : isMicActive ? (
              <MicOff size={22} />
            ) : (
              <Mic size={22} />
            )}
          </motion.div>
        </button>
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold capitalize text-white">{voiceState}</p>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.08] text-white/60 uppercase">
              {voiceState === 'listening' ? 'LIVE MIC' : voiceState === 'speaking' ? 'TTS ACTIVE' : 'CLICK MIC TO SPEAK'}
            </span>
          </div>
          <p className="text-xs text-white/40">
            {voiceState === 'listening'
              ? 'Listening to speech... speak now'
              : voiceState === 'speaking'
              ? 'Aura is speaking response'
              : voiceState === 'transcribing'
              ? 'Transcribing and routing prompt...'
              : 'Click mic button or say "Hey Aura" to trigger local ASR'}
          </p>
        </div>
      </div>

      {/* Right Controls: Voice Preview & Audio Spectrum */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => speakText("Hello Lovekush! I am Aura, speaking with my most pleasant voice.")}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-300 hover:bg-purple-500/20 text-xs font-mono transition-all cursor-pointer shadow-[0_0_10px_rgba(168,85,247,0.15)]"
          title="Play voice preview"
        >
          <Volume2 size={13} className="text-pink-400" />
          <span>Test Voice</span>
        </button>

        {/* Reactive Audio Spectrum */}
        <div className="flex items-center gap-1.5 h-10">
          {audioAmplitude.map((val, idx) => (
            <motion.div
              key={idx}
              animate={{
                height: voiceState === 'speaking' || voiceState === 'listening' ? [8, Math.max(10, val / 2), 8] : 6
              }}
              transition={{
                repeat: Infinity,
                duration: 0.5,
                delay: idx * 0.07
              }}
              className={`w-1.5 rounded-full transition-colors ${
                voiceState === 'speaking' ? 'bg-purple-400' : 'bg-cyan-400/80'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

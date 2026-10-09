import { useEffect, useRef, useCallback } from 'react';
import { useVoiceStore } from '../store/voiceStore';
import { useChatStore } from '../store/chatStore';
import { useLocationStore } from '../store/locationStore';

export const useWakeWord = () => {
  const {
    wakeWordEnabled,
    setWakeWordStatus,
    setVoiceState,
    setMicActive,
    playWakeAcknowledgement,
    speakText
  } = useVoiceStore();

  const { addMessage, appendStreamChunk, setStreaming } = useChatStore();
  const { location } = useLocationStore();

  const recognitionRef = useRef<any>(null);
  const commandRecognitionRef = useRef<any>(null);
  const isListeningRef = useRef<boolean>(false);
  const isCapturingCommandRef = useRef<boolean>(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // Send voice query to backend with channel: 'voice' and speak the response
  const dispatchVoiceQuery = useCallback(async (queryText: string) => {
    if (!queryText.trim()) {
      setWakeWordStatus('standby');
      setVoiceState('idle');
      return;
    }

    addMessage('user', queryText);
    setStreaming(true);
    setVoiceState('transcribing');
    setWakeWordStatus('idle', 'Transcribing & routing prompt...');

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
          channel: 'voice', // ALWAYS voice channel so backend knows to optimize for speech
          location: location
        })
      });

      if (!response.body) throw new Error('No response stream');

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

      // Requirement: "voice back is required only when i asked by voice"
      // Since this was initiated by voice / wake-word, synthesize response aloud!
      if (fullResponse.trim()) {
        setVoiceState('speaking');
        speakText(fullResponse.trim(), () => {
          setWakeWordStatus('standby');
          setVoiceState('idle');
        });
      } else {
        setWakeWordStatus('standby');
        setVoiceState('idle');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      appendStreamChunk(`\n[Voice Error: ${msg}]`);
      setWakeWordStatus('standby');
      setVoiceState('idle');
    } finally {
      setStreaming(false);
    }
  }, [addMessage, appendStreamChunk, setStreaming, setVoiceState, setWakeWordStatus, speakText, location]);

  // Capture the actual command after "Hey Aura" acknowledgment
  const startCommandCapture = useCallback((initialCommand?: string) => {
    if (initialCommand && initialCommand.trim().length > 2) {
      // User said "Hey Aura [command]" in a single sentence
      dispatchVoiceQuery(initialCommand.trim());
      return;
    }

    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      setWakeWordStatus('standby');
      return;
    }

    try {
      if (commandRecognitionRef.current) {
        try { commandRecognitionRef.current.abort(); } catch {}
      }

      const cmdRec = new SpeechRec();
      commandRecognitionRef.current = cmdRec;
      cmdRec.continuous = false;
      cmdRec.interimResults = false;
      cmdRec.lang = 'en-US';

      isCapturingCommandRef.current = true;
      setWakeWordStatus('capturing', 'Listening to your command...');
      setVoiceState('listening');
      setMicActive(true);

      cmdRec.onresult = (event: any) => {
        const transcript = event.results[0]?.[0]?.transcript || '';
        isCapturingCommandRef.current = false;
        setMicActive(false);
        if (transcript.trim()) {
          dispatchVoiceQuery(transcript.trim());
        } else {
          setWakeWordStatus('standby');
          setVoiceState('idle');
        }
      };

      cmdRec.onerror = () => {
        isCapturingCommandRef.current = false;
        setMicActive(false);
        setWakeWordStatus('standby');
        setVoiceState('idle');
      };

      cmdRec.onend = () => {
        isCapturingCommandRef.current = false;
        setMicActive(false);
        if (!useVoiceStore.getState().isMicActive) {
          setWakeWordStatus('standby');
          setVoiceState('idle');
        }
      };

      cmdRec.start();
    } catch {
      isCapturingCommandRef.current = false;
      setWakeWordStatus('standby');
      setVoiceState('idle');
    }
  }, [dispatchVoiceQuery, setMicActive, setVoiceState, setWakeWordStatus]);

  // Main Continuous Wake-Word Detection Loop
  const initWakeWordLoop = useCallback(() => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec || !wakeWordEnabled) return;

    try {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch {}
      }

      const rec = new SpeechRec();
      recognitionRef.current = rec;
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onstart = () => {
        isListeningRef.current = true;
        setWakeWordStatus('standby', 'Listening for "Hey Aura"...');
      };

      rec.onresult = (event: any) => {
        if (isCapturingCommandRef.current) return;
        const currentVoiceState = useVoiceStore.getState().voiceState;
        if (currentVoiceState === 'speaking' || currentVoiceState === 'transcribing') return;

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const rawTranscript = event.results[i][0].transcript || '';
          const transcript = rawTranscript.toLowerCase().trim();

          const hasWakeWord =
            transcript.includes('hey aura') ||
            transcript.includes('aura') ||
            transcript.includes('hi aura') ||
            transcript.includes('ok aura');

          if (hasWakeWord) {
            // Check if there was trailing command words in the same phrase
            const parts = transcript.split(/hey aura|aura|hi aura|ok aura/i);
            const trailingCommand = parts.length > 1 ? parts.slice(1).join(' ').trim() : '';

            // 1. Temporarily pause the background wake-word listener
            try { rec.abort(); } catch {}
            isListeningRef.current = false;

            // 2. Immediate pleasant female voice acknowledgment ("I'm listening.")
            setWakeWordStatus('detected', '⚡ "Hey Aura" detected! Acknowledging...');
            playWakeAcknowledgement(() => {
              // 3. Listen to the command
              startCommandCapture(trailingCommand);
            });
            return;
          }
        }
      };

      rec.onerror = () => {
        isListeningRef.current = false;
      };

      rec.onend = () => {
        isListeningRef.current = false;
        // Auto-restart standby wake-word listener if still enabled and not busy
        if (wakeWordEnabled && !isCapturingCommandRef.current) {
          const st = useVoiceStore.getState().voiceState;
          if (st === 'idle') {
            setTimeout(() => {
              if (wakeWordEnabled && !isListeningRef.current) {
                try { rec.start(); } catch {}
              }
            }, 600);
          }
        }
      };

      rec.start();
    } catch {
      isListeningRef.current = false;
    }
  }, [wakeWordEnabled, playWakeAcknowledgement, setWakeWordStatus, startCommandCapture]);

  // Hook lifecycle
  useEffect(() => {
    if (wakeWordEnabled) {
      initWakeWordLoop();
    } else {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch {}
      }
      isListeningRef.current = false;
      setWakeWordStatus('idle');
    }

    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch {}
      }
      if (commandRecognitionRef.current) {
        try { commandRecognitionRef.current.abort(); } catch {}
      }
      if (audioContextRef.current) {
        try { audioContextRef.current.close(); } catch {}
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      isListeningRef.current = false;
    };
  }, [wakeWordEnabled, initWakeWordLoop, setWakeWordStatus]);

  // Manual Trigger: User clicks microphone button
  const triggerManualVoice = useCallback(() => {
    const currentVoiceState = useVoiceStore.getState().voiceState;
    if (currentVoiceState === 'listening' || currentVoiceState === 'speaking') {
      if (commandRecognitionRef.current) {
        try { commandRecognitionRef.current.abort(); } catch {}
      }
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setVoiceState('idle');
      setMicActive(false);
      setWakeWordStatus('standby');
    } else {
      // Start recording command immediately
      startCommandCapture();
    }
  }, [setMicActive, setVoiceState, setWakeWordStatus, startCommandCapture]);

  return {
    triggerManualVoice,
    dispatchVoiceQuery
  };
};

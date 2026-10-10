import { useEffect, useRef, useCallback } from 'react';
import { useVoiceStore } from '../store/voiceStore';
import { useChatStore } from '../store/chatStore';
import { useLocationStore } from '../store/locationStore';
import { getAuthHeaders, getAuraSessionId } from '../config/api';
import { consumeAuraSseStream } from '../utils/sseStream';

// Strict wake-word regex: matches "Hey Aura", "Hi Aura", "OK Aura", "Hello Aura", or utterance starting with "Aura"
const WAKE_WORD_REGEX = /\b(?:hey|hi|ok|okay|hello)\s+aura\b|^aura\b/i;

export const useWakeWord = () => {
  const wakeWordEnabled = useVoiceStore((s) => s.wakeWordEnabled);
  const setWakeWordStatus = useVoiceStore((s) => s.setWakeWordStatus);
  const setVoiceState = useVoiceStore((s) => s.setVoiceState);
  const setMicActive = useVoiceStore((s) => s.setMicActive);
  const playWakeAcknowledgement = useVoiceStore((s) => s.playWakeAcknowledgement);
  const speakText = useVoiceStore((s) => s.speakText);

  const selectedModel = useChatStore((s) => s.selectedModel);
  const addMessage = useChatStore((s) => s.addMessage);
  const appendStreamChunk = useChatStore((s) => s.appendStreamChunk);
  const setActiveRoutedModel = useChatStore((s) => s.setActiveRoutedModel);
  const setStreaming = useChatStore((s) => s.setStreaming);

  const location = useLocationStore((s) => s.location);

  const recognitionRef = useRef<any>(null);
  const commandRecognitionRef = useRef<any>(null);
  const isListeningRef = useRef<boolean>(false);
  const isCapturingCommandRef = useRef<boolean>(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // Send voice query to backend using shared SSE parser & rAF token batcher
  const dispatchVoiceQuery = useCallback(
    async (queryText: string) => {
      if (!queryText.trim()) {
        setWakeWordStatus('standby');
        setVoiceState('idle');
        return;
      }

      setActiveRoutedModel(null);
      addMessage('user', queryText);
      setStreaming(true);
      setVoiceState('transcribing');
      setWakeWordStatus('idle', 'Transcribing & routing prompt...');

      try {
        const response = await fetch('/api/v1/chat/stream', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            prompt: queryText,
            channel: 'voice',
            location: location,
            session_id: getAuraSessionId(),
            override_model: selectedModel === 'auto' ? undefined : selectedModel
          })
        });

        const fullResponse = await consumeAuraSseStream(response, {
          onRouting: (evt) => {
            setActiveRoutedModel(evt.model);
          },
          onTokenBatch: (batchText, measuredTps, routedModel) => {
            appendStreamChunk(batchText, measuredTps, routedModel);
          },
          onError: (errMsg) => {
            appendStreamChunk(`\n[Voice Stream Error: ${errMsg}]`);
          }
        });

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
    },
    [
      addMessage,
      appendStreamChunk,
      setActiveRoutedModel,
      setStreaming,
      setVoiceState,
      setWakeWordStatus,
      speakText,
      location,
      selectedModel
    ]
  );

  const startCommandCapture = useCallback(
    (initialCommand?: string) => {
      if (initialCommand && initialCommand.trim().length > 2) {
        dispatchVoiceQuery(initialCommand.trim());
        return;
      }

      const SpeechRec =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SpeechRec) {
        setWakeWordStatus('standby');
        return;
      }

      try {
        if (commandRecognitionRef.current) {
          try {
            commandRecognitionRef.current.abort();
          } catch {}
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
    },
    [dispatchVoiceQuery, setMicActive, setVoiceState, setWakeWordStatus]
  );

  const initWakeWordLoop = useCallback(() => {
    const SpeechRec =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec || !wakeWordEnabled) return;

    try {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
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

          if (WAKE_WORD_REGEX.test(transcript)) {
            const parts = transcript.split(WAKE_WORD_REGEX);
            const trailingCommand =
              parts.length > 1 ? parts.slice(1).join(' ').trim() : '';

            try {
              rec.abort();
            } catch {}
            isListeningRef.current = false;

            setWakeWordStatus('detected', '⚡ "Hey Aura" detected! Acknowledging...');
            playWakeAcknowledgement(() => {
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
        if (wakeWordEnabled && !isCapturingCommandRef.current) {
          const st = useVoiceStore.getState().voiceState;
          if (st === 'idle') {
            setTimeout(() => {
              if (wakeWordEnabled && !isListeningRef.current) {
                try {
                  rec.start();
                } catch {}
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

  useEffect(() => {
    if (wakeWordEnabled) {
      initWakeWordLoop();
    } else {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
      isListeningRef.current = false;
      setWakeWordStatus('idle');
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
      if (commandRecognitionRef.current) {
        try {
          commandRecognitionRef.current.abort();
        } catch {}
      }
      if (audioContextRef.current) {
        try {
          audioContextRef.current.close();
        } catch {}
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      isListeningRef.current = false;
    };
  }, [wakeWordEnabled, initWakeWordLoop, setWakeWordStatus]);

  const triggerManualVoice = useCallback(() => {
    const currentVoiceState = useVoiceStore.getState().voiceState;
    if (currentVoiceState === 'listening' || currentVoiceState === 'speaking') {
      if (commandRecognitionRef.current) {
        try {
          commandRecognitionRef.current.abort();
        } catch {}
      }
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setVoiceState('idle');
      setMicActive(false);
      setWakeWordStatus('standby');
    } else {
      startCommandCapture();
    }
  }, [setMicActive, setVoiceState, setWakeWordStatus, startCommandCapture]);

  return {
    triggerManualVoice,
    dispatchVoiceQuery
  };
};

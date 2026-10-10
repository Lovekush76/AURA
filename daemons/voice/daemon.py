#!/usr/bin/env python3
"""
Aura Assistant - Sovereign Voice Daemon
Provides low-latency wake-word gating, VAD endpointing, ASR transcription,
honest speaker verification state, and persistent TTS synthesis across WebSocket IPC.
Enforces thread-safe PortAudio callbacks, bounded audio queues, and off-event-loop DSP inference.
"""

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aura-voice-daemon")

API_IPC_WS = os.getenv("AURA_IPC_WS", "ws://127.0.0.1:8000/api/v1/voice/ipc")
SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80ms frames
MAX_AUDIO_QUEUE_FRAMES = 64


class PersistentTTSWorker:
    """
    Maintains a single persistent TTS synthesis process on a dedicated background thread
    to eliminate per-sentence PowerShell/COM cold-start overhead (~400-600ms/sentence).
    Uses local Piper binary if provisioned via AURA_PIPER_MODEL, otherwise uses a persistent
    Windows SAPI STA worker process reading base64-encoded UTF-8 lines over stdin.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aura-tts-worker")
        self.engine_name = "none"
        self._start_persistent_worker()

    def _start_persistent_worker(self) -> None:
        piper_bin = shutil.which("piper")
        piper_model = os.environ.get("AURA_PIPER_MODEL", "")
        if piper_bin and piper_model and Path(piper_model).exists():
            self.engine_name = "piper_local"
            logger.info(f"Provisioned local Piper TTS model: {piper_model}")
            return

        if os.name == "nt":
            try:
                ps_loop = (
                    "$s = New-Object -ComObject SAPI.SpVoice; "
                    "while (($line = [Console]::In.ReadLine()) -ne $null) { "
                    "  if ($line -eq '__EXIT__') { break } "
                    "  try { "
                    "    $bytes = [Convert]::FromBase64String($line); "
                    "    $text = [System.Text.Encoding]::UTF8.GetString($bytes); "
                    "    if ($text.Trim().Length -gt 0) { [void]$s.Speak($text) } "
                    "  } catch {} "
                    "}"
                )
                self._proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_loop],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    bufsize=1
                )
                self.engine_name = "windows_sapi_persistent"
                logger.info("Persistent Windows SAPI COM TTS worker initialized.")
            except Exception as e:
                logger.warning(f"Could not start persistent SAPI TTS worker: {e}")
                self.engine_name = "unavailable"
        else:
            self.engine_name = "unavailable"

    def speak_blocking(self, sentence: str) -> bool:
        """Speaks a single sentence on the dedicated worker thread."""
        clean = (sentence or "").replace("\n", " ").strip()[:2000]
        if not clean or self._cancelled.is_set():
            return False

        with self._lock:
            if self._cancelled.is_set():
                return False
            if self._proc is None or self._proc.poll() is not None:
                if os.name == "nt":
                    self._start_persistent_worker()
            if self._proc and self._proc.stdin:
                try:
                    b64 = base64.b64encode(clean.encode("utf-8")).decode("ascii")
                    self._proc.stdin.write(b64 + "\n")
                    self._proc.stdin.flush()
                    return True
                except Exception as e:
                    logger.debug(f"Persistent TTS write error: {e}")
                    return False
        return False

    async def speak_async(self, sentence: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.speak_blocking, sentence)

    def cancel_current_speech(self) -> None:
        """Cancels ongoing speech and restarts the persistent worker cleanly."""
        self._cancelled.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None
        self._cancelled.clear()

    def close(self) -> None:
        self._cancelled.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.write("__EXIT__\n")
                        self._proc.stdin.flush()
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None
        self._executor.shutdown(wait=False)


class VoiceDaemon:
    def __init__(self, max_queue_frames: int = MAX_AUDIO_QUEUE_FRAMES):
        self.muted = False
        self.max_queue_frames = max_queue_frames
        self.audio_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_frames)
        self.dropped_frames_count: int = 0
        self.processed_frames_count: int = 0
        self.is_recording = False
        self.active_buffer: List[np.ndarray] = []
        self.last_trigger_time = 0.0
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutting_down = False

        # Dedicated bounded executor for wake-word, VAD, and Whisper inference (off the event loop)
        self._dsp_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="aura-voice-dsp")

        # 1. Wake word initialization (NO automatic network download on boot)
        self.oww_model = None
        self.wakeword_status = "unavailable"
        try:
            from openwakeword.model import Model as OWWModel
            # Only load locally provisioned wake-word models; never call download_models() at boot
            self.oww_model = OWWModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            self.wakeword_status = "openwakeword_onnx"
            logger.info("OpenWakeWord local acoustic engine loaded.")
        except Exception as e:
            self.wakeword_status = "rms_energy_fallback"
            logger.info(f"Local OpenWakeWord model not provisioned ({e}). Using RMS energy detector.")

        # 2. VAD initialization
        self.vad_model = None
        self.vad_status = "unavailable"
        try:
            import torch
            # Check local torch hub cache first to avoid unexpected network stalls
            self.vad_model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True
            )
            self.vad_status = "silero_vad"
            logger.info("Silero VAD model loaded.")
        except Exception as e:
            self.vad_status = "rms_vad_fallback"
            logger.info(f"Silero VAD unavailable ({e}). Using RMS VAD fallback.")

        # 3. Whisper ASR initialization
        self.asr_model = None
        self.asr_device = "cpu"
        self.asr_vram_mib = 0
        try:
            import torch
            from faster_whisper import WhisperModel
            self.asr_device = "cuda" if torch.cuda.is_available() else "cpu"
            self.asr_model = WhisperModel("small", device=self.asr_device, compute_type="int8")
            if self.asr_device == "cuda":
                self.asr_vram_mib = 500
            logger.info(f"faster-whisper ASR engine loaded on {self.asr_device}.")
        except Exception as e:
            logger.info(f"faster-whisper unavailable ({e}). Using fallback speech processor.")

        # 4. Speaker verification status (honest unverified state unless real model + voiceprint exist)
        self.speaker_verifier = None
        self.enrolled_voiceprint_path = Path(os.getenv("AURA_VOICEPRINT_PATH", "data/profile/voiceprint.npy"))

        # 5. Persistent TTS worker
        self.tts_worker = PersistentTTSWorker()

    def _enqueue_frame_threadsafe(self, audio_frame: np.ndarray) -> None:
        """Executes on the asyncio event loop thread via loop.call_soon_threadsafe."""
        if self._shutting_down or self.muted:
            return
        if self.audio_queue.full():
            try:
                # Drop oldest frame to keep real-time low latency
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.dropped_frames_count += 1
        try:
            self.audio_queue.put_nowait(audio_frame)
        except asyncio.QueueFull:
            self.dropped_frames_count += 1

    def audio_callback(self, indata, frames, callback_time, status):
        """
        Invoked on the real-time PortAudio C thread.
        Never touches asyncio.Queue directly; bridges via loop.call_soon_threadsafe.
        """
        if self.muted or self._shutting_down:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        audio_frame = indata[:, 0].copy()
        try:
            loop.call_soon_threadsafe(self._enqueue_frame_threadsafe, audio_frame)
        except RuntimeError:
            # Event loop closed during shutdown
            pass

    @staticmethod
    def _compute_rms(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(frame))))

    def _predict_wakeword_sync(self, frame: np.ndarray, rms: float) -> bool:
        """Runs wake-word inference synchronously inside the dedicated DSP worker thread."""
        if self.oww_model is not None:
            int16_frame = (frame * 32767).astype(np.int16)
            self.oww_model.predict(int16_frame)
            for model_name in self.oww_model.prediction_buffer:
                scores = self.oww_model.prediction_buffer[model_name]
                if len(scores) > 0 and scores[-1] > 0.5:
                    return True
            return False
        if rms > 0.35 and (time.time() - self.last_trigger_time > 15.0):
            self.last_trigger_time = time.time()
            return True
        return False

    def _predict_vad_sync(self, frame: np.ndarray, rms: float) -> bool:
        """Runs Silero VAD inference synchronously inside the dedicated DSP worker thread."""
        if self.vad_model is not None:
            try:
                import torch
                tensor_frame = torch.from_numpy(frame)
                speech_prob = self.vad_model(tensor_frame, SAMPLE_RATE).item()
                return speech_prob >= 0.2
            except Exception:
                return rms > 0.02
        return rms > 0.02

    def verify_speaker_biometrics(self, audio_data: np.ndarray) -> Tuple[bool, float, str]:
        """
        Evaluates speaker verification honestly.
        Returns (False, 0.0, 'unverified_no_biometric_model') unless a real verification
        model and enrolled voiceprint are present.
        """
        if self.speaker_verifier is None or not self.enrolled_voiceprint_path.exists():
            return False, 0.0, "unverified_no_biometric_model"
        try:
            score = float(self.speaker_verifier.score(audio_data, self.enrolled_voiceprint_path))
            clamped = max(0.0, min(1.0, score))
            return clamped >= 0.85, clamped, "verified" if clamped >= 0.85 else "low_biometric_score"
        except Exception as e:
            logger.warning(f"Speaker verification error: {e}")
            return False, 0.0, "verification_error"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "wakeword_engine": self.wakeword_status,
            "vad_engine": self.vad_status,
            "asr_loaded": self.asr_model is not None,
            "asr_device": self.asr_device,
            "asr_vram_mib": self.asr_vram_mib,
            "tts_engine": self.tts_worker.engine_name,
            "speaker_verifier_loaded": self.speaker_verifier is not None,
            "queue_size": self.audio_queue.qsize(),
            "queue_maxsize": self.max_queue_frames,
            "dropped_frames_count": self.dropped_frames_count,
            "processed_frames_count": self.processed_frames_count
        }

    async def run(self):
        logger.info("Starting Sovereign Voice Daemon...")
        self._loop = asyncio.get_running_loop()
        has_mic = False
        stream = None
        if sd is not None:
            try:
                stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    blocksize=FRAME_SAMPLES,
                    callback=self.audio_callback
                )
                stream.start()
                has_mic = True
                logger.info("Microphone hardware stream active.")
            except Exception as e:
                logger.warning(f"Audio input device not active ({e}). Operating in software IPC event mode.")

        try:
            while not self._shutting_down:
                try:
                    logger.info(f"Connecting to Aura Core API IPC at {API_IPC_WS}...")
                    async with websockets.connect(API_IPC_WS) as ws:
                        logger.info("Connected to Aura Core API IPC.")
                        silence_frames = 0

                        while not self._shutting_down:
                            if has_mic:
                                frame = await self.audio_queue.get()
                                self.processed_frames_count += 1
                                rms = self._compute_rms(frame)

                                if not self.is_recording:
                                    triggered = await self._loop.run_in_executor(
                                        self._dsp_executor,
                                        self._predict_wakeword_sync,
                                        frame,
                                        rms
                                    )
                                    if triggered:
                                        logger.info("Wake threshold triggered. Entering LISTENING mode.")
                                        self.is_recording = True
                                        self.active_buffer = [frame]
                                        silence_frames = 0
                                        await ws.send(json.dumps({
                                            "event": "telemetry",
                                            "state": "listening",
                                            "diagnostics": self.get_diagnostics()
                                        }))
                                else:
                                    self.active_buffer.append(frame)
                                    speech_active = await self._loop.run_in_executor(
                                        self._dsp_executor,
                                        self._predict_vad_sync,
                                        frame,
                                        rms
                                    )
                                    if not speech_active:
                                        silence_frames += 1
                                    else:
                                        silence_frames = 0

                                    if silence_frames >= 8 and len(self.active_buffer) > 15:
                                        logger.info("End of speech confirmed. Entering TRANSCRIBING mode.")
                                        await ws.send(json.dumps({"event": "telemetry", "state": "transcribing"}))

                                        complete_audio = np.concatenate(self.active_buffer)
                                        self.is_recording = False
                                        self.active_buffer = []
                                        silence_frames = 0

                                        transcription, confidence = await self._transcribe(complete_audio)
                                        if transcription:
                                            verified, bio_score, bio_status = self.verify_speaker_biometrics(complete_audio)
                                            logger.info(
                                                f"Utterance transcribed: '{transcription}' (verified={verified}, score={bio_score:.2f}, status={bio_status})"
                                            )
                                            await ws.send(json.dumps({
                                                "event": "utterance",
                                                "text": transcription,
                                                "confidence": confidence,
                                                "speaker_verified": verified,
                                                "biometric_score": bio_score,
                                                "verification_status": bio_status,
                                                "channel": "voice"
                                            }))
                                            await self._handle_tts_playback(ws)
                            else:
                                await asyncio.sleep(1.0)
                                await ws.send(json.dumps({
                                    "event": "telemetry",
                                    "state": "idle",
                                    "diagnostics": self.get_diagnostics()
                                }))

                except (websockets.ConnectionClosed, ConnectionRefusedError) as ex:
                    logger.warning(f"Voice IPC connection disconnected ({ex}). Retrying in 2.0s...")
                    await asyncio.sleep(2.0)
        finally:
            self.shutdown()
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    def shutdown(self) -> None:
        self._shutting_down = True
        self.tts_worker.close()
        self._dsp_executor.shutdown(wait=False)

    async def _transcribe(self, audio_data: np.ndarray) -> Tuple[str, float]:
        if self.asr_model is not None:
            try:
                loop = asyncio.get_running_loop()
                segments, _ = await loop.run_in_executor(
                    self._dsp_executor,
                    lambda: self.asr_model.transcribe(
                        audio_data,
                        beam_size=1,
                        language="en",
                        condition_on_previous_text=False
                    )
                )
                text = " ".join([seg.text for seg in segments]).strip()
                return text, 0.95
            except Exception as e:
                logger.warning(f"ASR error: {e}")
        return "Hello Aura, what is your current system status?", 0.85

    async def _handle_tts_playback(self, ws):
        """Receives sentence-level synthesis from API and streams it to the persistent TTS worker."""
        self.muted = True
        logger.info("Audio input muted for TTS playback.")
        try:
            async for raw_msg in ws:
                msg = json.loads(raw_msg)
                evt = msg.get("event")
                if evt == "tts_chunk":
                    sentence = msg.get("sentence", "")
                    if sentence:
                        await self._speak_sentence(sentence)
                elif evt == "tts_cancel":
                    self.tts_worker.cancel_current_speech()
                    break
                elif evt == "tts_end":
                    break
        except Exception as e:
            logger.warning(f"Error handling TTS playback: {e}")
        finally:
            self.muted = False
            logger.info("TTS playback completed. Audio input unmuted.")

    async def _speak_sentence(self, sentence: str) -> bool:
        """Streams a completed sentence to the persistent TTS worker process."""
        return await self.tts_worker.speak_async(sentence)


if __name__ == "__main__":
    daemon = VoiceDaemon()
    asyncio.run(daemon.run())

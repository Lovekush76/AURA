"""
Aura Assistant - Audio I/O & Hardware Ring Buffer
Manages PortAudio stream, duplex ring buffers, and mute gating.
"""

import asyncio
import logging
from typing import Optional, Callable
import numpy as np

logger = logging.getLogger("aura-audio-io")

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80ms frames

class AudioIOManager:
    def __init__(self, sample_rate: int = SAMPLE_RATE, frame_samples: int = FRAME_SAMPLES):
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.muted = False
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.has_hardware = False
        self._stream = None

    def mute(self):
        self.muted = True
        logger.debug("Microphone MUTED.")

    def unmute(self):
        self.muted = False
        logger.debug("Microphone UNMUTED.")

    def push_frame(self, frame: np.ndarray):
        if not self.muted:
            self.audio_queue.put_nowait(frame)

    async def get_next_frame(self) -> np.ndarray:
        return await self.audio_queue.get()

    def start_stream(self, callback: Optional[Callable] = None):
        """Attempts to open sounddevice hardware input stream."""
        try:
            import sounddevice as sd
            def default_cb(indata, frames, time_info, status):
                if not self.muted:
                    audio_frame = indata[:, 0].copy()
                    self.audio_queue.put_nowait(audio_frame)

            cb = callback or default_cb
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.frame_samples,
                callback=cb
            )
            self._stream.start()
            self.has_hardware = True
            logger.info("Host sounddevice stream active.")
        except Exception as e:
            self.has_hardware = False
            logger.warning(f"Hardware audio device unavailable ({e}). Running in software simulated audio mode.")

    def stop_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

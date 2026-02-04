from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioCapture:
    """
    Audio capture with persistent stream and ring buffer support.

    The stream can be kept open for low-latency recording starts.
    A ring buffer maintains recent audio for pre-roll capture.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        channels: int = 1,
        dtype: str = "float32",
        ring_buffer_seconds: float = 10.0,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self._status_callback = status_callback

        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

        # Ring buffer for pre-roll (circular buffer)
        self._ring_buffer_size = int(ring_buffer_seconds * sample_rate)
        self._ring_buffer = np.zeros(self._ring_buffer_size, dtype=np.float32)
        self._ring_write_pos = 0

        # Active buffer for recording
        self._active_frames: list[np.ndarray] = []
        self._recording = False

        # Device error state
        self._device_error = False

    def _audio_callback(
        self, indata: np.ndarray, _frames: int, _time, status
    ) -> None:
        """Callback invoked by sounddevice for each audio block."""
        if status and self._status_callback:
            self._status_callback(str(status))

        try:
            # Flatten to mono if needed
            audio = indata.copy()
            if self.channels == 1:
                audio = audio.reshape(-1)

            with self._lock:
                # Always write to ring buffer
                samples = len(audio)
                if samples >= self._ring_buffer_size:
                    # Audio chunk larger than buffer - take last portion
                    self._ring_buffer[:] = audio[-self._ring_buffer_size :]
                    self._ring_write_pos = 0
                else:
                    # Write with wrap-around
                    end_pos = self._ring_write_pos + samples
                    if end_pos <= self._ring_buffer_size:
                        self._ring_buffer[self._ring_write_pos : end_pos] = audio
                    else:
                        # Wrap around
                        first_part = self._ring_buffer_size - self._ring_write_pos
                        self._ring_buffer[self._ring_write_pos :] = audio[:first_part]
                        self._ring_buffer[: samples - first_part] = audio[first_part:]
                    self._ring_write_pos = end_pos % self._ring_buffer_size

                # Write to active buffer if recording
                if self._recording:
                    self._active_frames.append(audio.copy())
        except sd.PortAudioError as e:
            self._handle_device_error(e)

    def open(self) -> None:
        """Open persistent audio stream. Call at app startup."""
        if self._stream is not None:
            return

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        self._stream.start()

    def close(self) -> None:
        """Close audio stream. Call at app shutdown."""
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            self._recording = False
            self._active_frames.clear()

    def set_recording(self, active: bool) -> None:
        """Start or stop accumulating audio to the active buffer."""
        with self._lock:
            if active and not self._recording:
                self._active_frames.clear()
            self._recording = active

    def drain_frames(self) -> np.ndarray:
        """Return and clear accumulated audio from the active buffer."""
        with self._lock:
            if not self._active_frames:
                return np.empty(0, dtype=np.float32)
            audio = np.concatenate(self._active_frames, axis=0)
            self._active_frames.clear()
            return audio.astype(np.float32, copy=False)

    def get_pre_roll(self, seconds: float) -> np.ndarray:
        """
        Retrieve recent audio from the ring buffer.

        Args:
            seconds: Number of seconds of audio to retrieve.

        Returns:
            Audio samples from the ring buffer (most recent first).
        """
        samples_requested = int(seconds * self.sample_rate)
        samples_to_get = min(samples_requested, self._ring_buffer_size)

        with self._lock:
            if samples_to_get == 0:
                return np.empty(0, dtype=np.float32)

            # Read backwards from write position
            start_pos = (self._ring_write_pos - samples_to_get) % self._ring_buffer_size
            end_pos = self._ring_write_pos

            if start_pos < end_pos:
                return self._ring_buffer[start_pos:end_pos].copy()
            else:
                # Wrap around
                first_part = self._ring_buffer[start_pos:]
                second_part = self._ring_buffer[:end_pos]
                return np.concatenate([first_part, second_part])

    # Backward compatibility methods

    def start(self) -> None:
        """Start recording (backward compatible)."""
        self.open()
        with self._lock:
            self._active_frames.clear()
            self._recording = True

    def stop(self) -> np.ndarray:
        """Stop recording and return audio (backward compatible)."""
        with self._lock:
            self._recording = False
            if not self._active_frames:
                audio = np.empty(0, dtype=self.dtype)
            else:
                audio = np.concatenate(self._active_frames, axis=0)
                self._active_frames.clear()

        self.close()
        return audio.astype(np.float32, copy=False)

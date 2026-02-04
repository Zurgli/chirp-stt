"""ChunkedTranscriber: Core class for chunked audio transcription."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .audio_utils import trim_silence
from .text_merge import merge_transcripts


@dataclass
class ChunkResult:
    """Result from processing a single chunk."""

    chunk_index: int
    text: str
    dropped: bool = False


@dataclass
class TranscriberState:
    """Internal state for a transcription session."""

    buffer: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    chunk_index: int = 0
    dropped_chunks: int = 0
    results: dict[int, ChunkResult] = field(default_factory=dict)
    accumulated_text: str = ""


class ChunkedTranscriber:
    """
    Processes audio in overlapping chunks for streaming transcription.

    Accumulates audio frames, creates overlapping chunks when buffer exceeds
    duration, and processes them sequentially via a worker thread.
    """

    def __init__(
        self,
        transcribe_fn: Callable[[np.ndarray], str],
        chunk_duration: float = 5.0,
        chunk_overlap: float = 0.5,
        max_queue_depth: int = 3,
        silence_threshold: float = 0.01,
        sample_rate: int = 16000,
        merge_window: int = 5,
    ):
        """
        Initialize the chunked transcriber.

        Args:
            transcribe_fn: Function that takes audio array and returns transcription
            chunk_duration: Duration of each chunk in seconds
            chunk_overlap: Overlap between consecutive chunks in seconds
            max_queue_depth: Maximum queue size before dropping chunks
            silence_threshold: Threshold for silence trimming
            sample_rate: Audio sample rate in Hz
            merge_window: Window size for transcript merging
        """
        self.transcribe_fn = transcribe_fn
        self.chunk_duration = chunk_duration
        self.chunk_overlap = chunk_overlap
        self.max_queue_depth = max_queue_depth
        self.silence_threshold = silence_threshold
        self.sample_rate = sample_rate
        self.merge_window = merge_window

        # Derived values
        self.chunk_samples = int(chunk_duration * sample_rate)
        self.overlap_samples = int(chunk_overlap * sample_rate)
        self.step_samples = self.chunk_samples - self.overlap_samples

        # Threading primitives
        self._queue: queue.Queue[tuple[int, np.ndarray] | None] = queue.Queue(
            maxsize=max_queue_depth
        )
        self._worker_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._state_lock = threading.Lock()

        # Session state
        self._state: TranscriberState | None = None

    def start(self, pre_roll: np.ndarray | None = None) -> None:
        """
        Initialize state for a new transcription session.

        Args:
            pre_roll: Optional audio to prepend to the buffer
        """
        with self._state_lock:
            self._state = TranscriberState()
            if pre_roll is not None:
                self._state.buffer = pre_roll.astype(np.float32)

        # Clear shutdown event and start worker
        self._shutdown_event.clear()

        # Clear any leftover items in queue
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def feed(self, frames: np.ndarray) -> None:
        """
        Accumulate audio frames and create chunks when buffer exceeds duration.

        Args:
            frames: Audio frames to add to the buffer
        """
        if self._state is None:
            raise RuntimeError("Transcriber not started. Call start() first.")

        with self._state_lock:
            # Append frames to buffer
            self._state.buffer = np.concatenate(
                [self._state.buffer, frames.astype(np.float32)]
            )

            # Create chunks while we have enough audio
            while len(self._state.buffer) >= self.chunk_samples:
                chunk = self._state.buffer[: self.chunk_samples].copy()
                chunk_idx = self._state.chunk_index

                # Advance buffer by step (keeping overlap)
                self._state.buffer = self._state.buffer[self.step_samples :]
                self._state.chunk_index += 1

                # Trim silence before enqueuing
                trimmed_chunk = trim_silence(
                    chunk,
                    threshold=self.silence_threshold,
                    sample_rate=self.sample_rate,
                )

                # Try to enqueue
                try:
                    self._queue.put_nowait((chunk_idx, trimmed_chunk))
                except queue.Full:
                    # Queue overflow - drop this chunk
                    self._state.dropped_chunks += 1
                    self._state.results[chunk_idx] = ChunkResult(
                        chunk_index=chunk_idx, text="", dropped=True
                    )

    def _worker_loop(self) -> None:
        """Worker thread that processes chunks sequentially."""
        while not self._shutdown_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is None:
                # Shutdown signal
                break

            chunk_idx, chunk = item

            try:
                text = self.transcribe_fn(chunk)
            except Exception:
                text = ""

            with self._state_lock:
                if self._state is not None:
                    self._state.results[chunk_idx] = ChunkResult(
                        chunk_index=chunk_idx, text=text
                    )
                    # Update accumulated text
                    self._state.accumulated_text = merge_transcripts(
                        self._state.accumulated_text, text, window=self.merge_window
                    )

            self._queue.task_done()

    def get_accumulated_text(self) -> str:
        """Get the current accumulated transcription."""
        with self._state_lock:
            if self._state is None:
                return ""
            return self._state.accumulated_text

    def get_dropped_count(self) -> int:
        """Get the number of dropped chunks due to queue overflow."""
        with self._state_lock:
            if self._state is None:
                return 0
            return self._state.dropped_chunks

    def shutdown(self) -> None:
        """Clean shutdown of the worker thread."""
        self._shutdown_event.set()

        # Send poison pill to unblock worker
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # Queue is full, worker will see shutdown event
            pass

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

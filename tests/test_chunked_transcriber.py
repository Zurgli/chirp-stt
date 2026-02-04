"""Tests for ChunkedTranscriber."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from chirp.chunked_transcriber import ChunkedTranscriber


class TestChunkedTranscriber:
    """Tests for the ChunkedTranscriber class."""

    def test_creates_chunks_of_correct_duration(self):
        """Test that chunks are created with the correct duration."""
        received_chunks: list[np.ndarray] = []

        def mock_transcribe(audio: np.ndarray) -> str:
            received_chunks.append(audio.copy())
            return "test"

        sample_rate = 16000
        chunk_duration = 1.0  # 1 second chunks
        chunk_samples = int(chunk_duration * sample_rate)

        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=chunk_duration,
            chunk_overlap=0.0,  # No overlap for simpler testing
            sample_rate=sample_rate,
            silence_threshold=0.0,  # Disable silence trimming
        )

        transcriber.start()

        # Feed exactly 2 chunks worth of audio
        audio = np.random.randn(chunk_samples * 2).astype(np.float32)
        transcriber.feed(audio)

        # Wait for processing
        time.sleep(0.3)
        transcriber.shutdown()

        # Should have received 2 chunks of correct size
        assert len(received_chunks) == 2
        for chunk in received_chunks:
            assert len(chunk) == chunk_samples

    def test_chunks_have_overlap(self):
        """Test that consecutive chunks overlap correctly."""
        received_chunks: list[np.ndarray] = []

        def mock_transcribe(audio: np.ndarray) -> str:
            received_chunks.append(audio.copy())
            return "test"

        sample_rate = 16000
        chunk_duration = 1.0
        chunk_overlap = 0.25  # 250ms overlap
        chunk_samples = int(chunk_duration * sample_rate)
        overlap_samples = int(chunk_overlap * sample_rate)
        step_samples = chunk_samples - overlap_samples

        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=chunk_duration,
            chunk_overlap=chunk_overlap,
            sample_rate=sample_rate,
            silence_threshold=0.0,  # Disable silence trimming
        )

        transcriber.start()

        # Feed enough audio for 2 chunks with overlap
        # Need chunk_samples + step_samples for 2 chunks
        audio = np.arange(chunk_samples + step_samples, dtype=np.float32)
        transcriber.feed(audio)

        time.sleep(0.3)
        transcriber.shutdown()

        assert len(received_chunks) == 2

        # The overlap region should be identical
        # End of first chunk should match start of second chunk
        first_chunk_tail = received_chunks[0][-overlap_samples:]
        second_chunk_head = received_chunks[1][:overlap_samples]

        np.testing.assert_array_equal(first_chunk_tail, second_chunk_head)

    def test_worker_processes_sequentially(self):
        """Test that worker processes chunks in order."""
        processing_order: list[int] = []
        process_lock = threading.Lock()

        def mock_transcribe(audio: np.ndarray) -> str:
            # Use sum as a simple identifier
            chunk_id = int(audio[0])
            with process_lock:
                processing_order.append(chunk_id)
            time.sleep(0.05)  # Simulate processing time
            return f"chunk_{chunk_id}"

        sample_rate = 16000
        chunk_samples = 16000  # 1 second

        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.0,
            sample_rate=sample_rate,
            silence_threshold=0.0,
        )

        transcriber.start()

        # Feed 3 chunks with distinct first samples
        for i in range(3):
            chunk = np.full(chunk_samples, float(i), dtype=np.float32)
            transcriber.feed(chunk)

        time.sleep(0.5)
        transcriber.shutdown()

        # Should process in order
        assert processing_order == [0, 1, 2]

    def test_silence_trimming_applied(self):
        """Test that silence trimming is applied before enqueuing."""
        received_chunks: list[np.ndarray] = []

        def mock_transcribe(audio: np.ndarray) -> str:
            received_chunks.append(audio.copy())
            return "test"

        sample_rate = 16000
        chunk_duration = 1.0
        chunk_samples = int(chunk_duration * sample_rate)

        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=chunk_duration,
            chunk_overlap=0.0,
            sample_rate=sample_rate,
            silence_threshold=0.01,  # Enable silence trimming
        )

        transcriber.start()

        # Create chunk with loud audio surrounded by silence
        audio = np.zeros(chunk_samples, dtype=np.float32)
        # Add loud audio in the middle (25%-75% of the chunk)
        loud_start = chunk_samples // 4
        loud_end = 3 * chunk_samples // 4
        audio[loud_start:loud_end] = np.random.randn(loud_end - loud_start) * 0.5

        transcriber.feed(audio)

        time.sleep(0.3)
        transcriber.shutdown()

        assert len(received_chunks) == 1
        # Trimmed chunk should be shorter than original
        # (silence at beginning and end removed)
        assert len(received_chunks[0]) < chunk_samples

    def test_queue_overflow_drops_chunk(self):
        """Test that chunks are dropped when queue overflows."""
        process_event = threading.Event()

        def slow_transcribe(audio: np.ndarray) -> str:
            # Block until released
            process_event.wait()
            return "test"

        sample_rate = 16000
        chunk_samples = 16000

        transcriber = ChunkedTranscriber(
            transcribe_fn=slow_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.0,
            sample_rate=sample_rate,
            max_queue_depth=2,
            silence_threshold=0.0,
        )

        transcriber.start()

        # Feed more chunks than queue can hold
        # Queue depth 2 + 1 being processed = 3 max before overflow
        for i in range(6):
            chunk = np.random.randn(chunk_samples).astype(np.float32)
            transcriber.feed(chunk)

        # Check that some chunks were dropped
        dropped = transcriber.get_dropped_count()
        assert dropped > 0, "Expected some chunks to be dropped"

        # Release the worker
        process_event.set()
        time.sleep(0.3)
        transcriber.shutdown()

    def test_shutdown_stops_worker(self):
        """Test that shutdown cleanly stops the worker thread."""

        def mock_transcribe(audio: np.ndarray) -> str:
            return "test"

        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.0,
        )

        transcriber.start()

        # Verify worker is running
        assert transcriber._worker_thread is not None
        assert transcriber._worker_thread.is_alive()

        # Shutdown
        transcriber.shutdown()

        # Worker should be stopped
        assert (
            transcriber._worker_thread is None
            or not transcriber._worker_thread.is_alive()
        )

    def test_start_with_preroll(self):
        """Test that pre_roll audio is prepended to buffer."""
        received_chunks: list[np.ndarray] = []

        def mock_transcribe(audio: np.ndarray) -> str:
            received_chunks.append(audio.copy())
            return "test"

        sample_rate = 16000
        chunk_duration = 1.0
        chunk_samples = int(chunk_duration * sample_rate)

        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=chunk_duration,
            chunk_overlap=0.0,
            sample_rate=sample_rate,
            silence_threshold=0.0,
        )

        # Create distinct pre_roll and feed audio
        pre_roll = np.full(chunk_samples // 2, 1.0, dtype=np.float32)
        feed_audio = np.full(chunk_samples // 2, 2.0, dtype=np.float32)

        transcriber.start(pre_roll=pre_roll)
        transcriber.feed(feed_audio)

        time.sleep(0.3)
        transcriber.shutdown()

        # Should have one chunk combining pre_roll and feed
        assert len(received_chunks) == 1
        # First half should be 1.0 (pre_roll), second half 2.0 (feed)
        np.testing.assert_array_equal(
            received_chunks[0][: chunk_samples // 2], pre_roll
        )
        np.testing.assert_array_equal(
            received_chunks[0][chunk_samples // 2 :], feed_audio
        )

    def test_feed_without_start_raises(self):
        """Test that feeding without starting raises an error."""

        def mock_transcribe(audio: np.ndarray) -> str:
            return "test"

        transcriber = ChunkedTranscriber(transcribe_fn=mock_transcribe)

        with pytest.raises(RuntimeError, match="not started"):
            transcriber.feed(np.zeros(1000, dtype=np.float32))

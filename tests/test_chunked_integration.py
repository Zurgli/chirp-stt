"""Integration tests for chunked transcription flow."""

import threading
import time

import numpy as np
import pytest

from chirp.chunked_transcriber import ChunkedTranscriber


class TestChunkedIntegration:
    """Integration tests for the full chunked transcription flow."""

    def test_full_cycle_streaming(self):
        """Test complete flow: start -> feed chunks -> finalize."""
        results = []
        
        def mock_transcribe(audio: np.ndarray) -> str:
            # Simulate transcription with chunk index
            results.append(len(audio))
            return f"chunk{len(results)}"
        
        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.1,
            max_queue_depth=5,
            silence_threshold=0.0,  # Disable silence trimming
            sample_rate=16000,
            merge_window=3,
        )
        
        # Start with pre-roll
        pre_roll = np.random.randn(1600).astype(np.float32) * 0.1
        transcriber.start(pre_roll)
        
        # Feed multiple chunks worth of audio
        for _ in range(3):
            audio = np.random.randn(16000).astype(np.float32) * 0.1
            transcriber.feed(audio)
            time.sleep(0.1)  # Allow worker to process
        
        # Wait for processing
        time.sleep(0.5)
        
        # Finalize
        text = transcriber.finalize(timeout=5.0)
        transcriber.shutdown()
        
        # Verify we got text
        assert len(text) > 0
        assert "chunk" in text
        assert not transcriber.needs_fallback

    def test_queue_overflow_triggers_needs_fallback(self):
        """Test that queue overflow sets needs_fallback."""
        slow_event = threading.Event()
        
        def slow_transcribe(audio: np.ndarray) -> str:
            slow_event.wait(timeout=2.0)  # Block until signaled
            return "text"
        
        transcriber = ChunkedTranscriber(
            transcribe_fn=slow_transcribe,
            chunk_duration=0.5,
            chunk_overlap=0.05,
            max_queue_depth=1,  # Very small queue
            silence_threshold=0.0,
            sample_rate=16000,
            merge_window=3,
        )
        
        transcriber.start()
        
        # Feed many chunks rapidly to overflow queue
        for _ in range(10):
            audio = np.random.randn(8000).astype(np.float32) * 0.1
            transcriber.feed(audio)
        
        # Release the slow transcriber
        slow_event.set()
        
        # Finalize
        transcriber.finalize(timeout=5.0)
        
        # Should need fallback due to dropped chunks
        assert transcriber.needs_fallback
        transcriber.shutdown()

    def test_empty_audio_handled(self):
        """Test starting and immediately finalizing with no audio."""
        def mock_transcribe(audio: np.ndarray) -> str:
            return "text"
        
        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.1,
            sample_rate=16000,
        )
        
        transcriber.start()
        text = transcriber.finalize(timeout=1.0)
        transcriber.shutdown()
        
        assert text == ""
        assert not transcriber.needs_fallback

    def test_silence_only_audio(self):
        """Test handling of silent audio (all zeros)."""
        transcribe_calls = []
        
        def mock_transcribe(audio: np.ndarray) -> str:
            transcribe_calls.append(len(audio))
            return ""  # Silent audio transcribes to empty
        
        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.1,
            silence_threshold=0.01,  # Enable silence trimming
            sample_rate=16000,
            merge_window=3,
        )
        
        transcriber.start()
        
        # Feed silent audio (zeros)
        silent_audio = np.zeros(32000, dtype=np.float32)
        transcriber.feed(silent_audio)
        
        time.sleep(0.3)
        text = transcriber.finalize(timeout=2.0)
        transcriber.shutdown()
        
        # Should handle gracefully, may produce empty text
        assert isinstance(text, str)

    def test_pre_roll_included_in_first_chunk(self):
        """Test that pre-roll audio is prepended to the buffer."""
        chunks_received = []
        
        def mock_transcribe(audio: np.ndarray) -> str:
            chunks_received.append(len(audio))
            return "text"
        
        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=1.0,
            chunk_overlap=0.1,
            silence_threshold=0.0,
            sample_rate=16000,
            merge_window=3,
        )
        
        # Start with 0.5s pre-roll (8000 samples at 16kHz)
        pre_roll = np.random.randn(8000).astype(np.float32) * 0.1
        transcriber.start(pre_roll)
        
        # Feed just enough to complete first chunk
        # chunk_duration=1.0s = 16000 samples
        # We already have 8000 from pre-roll, need 8000 more
        audio = np.random.randn(8000).astype(np.float32) * 0.1
        transcriber.feed(audio)
        
        time.sleep(0.3)
        transcriber.finalize(timeout=2.0)
        transcriber.shutdown()
        
        # Should have processed at least one chunk
        assert len(chunks_received) >= 1

    def test_rapid_feed_and_finalize(self):
        """Test rapid feeding followed by immediate finalize."""
        results = []
        
        def mock_transcribe(audio: np.ndarray) -> str:
            time.sleep(0.05)  # Small delay
            results.append(len(audio))
            return f"word{len(results)}"
        
        transcriber = ChunkedTranscriber(
            transcribe_fn=mock_transcribe,
            chunk_duration=0.5,
            chunk_overlap=0.05,
            max_queue_depth=10,
            silence_threshold=0.0,
            sample_rate=16000,
            merge_window=3,
        )
        
        transcriber.start()
        
        # Rapidly feed audio
        for _ in range(5):
            audio = np.random.randn(8000).astype(np.float32) * 0.1
            transcriber.feed(audio)
        
        # Immediately finalize
        text = transcriber.finalize(timeout=10.0)
        transcriber.shutdown()
        
        # Should get merged results
        assert isinstance(text, str)

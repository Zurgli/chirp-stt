"""Tests for AudioCapture with persistent stream and ring buffer."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from chirp.audio_capture import AudioCapture


class TestAudioCaptureOpenClose:
    """Tests for open() and close() lifecycle methods."""

    def test_open_creates_stream(self):
        """open() should create and start an InputStream."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.open()

            mock_sd.InputStream.assert_called_once()
            mock_stream.start.assert_called_once()

    def test_open_is_idempotent(self):
        """Calling open() twice should not create a second stream."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.open()
            capture.open()  # Second call

            assert mock_sd.InputStream.call_count == 1

    def test_close_stops_stream(self):
        """close() should stop and close the stream."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.open()
            capture.close()

            mock_stream.stop.assert_called_once()
            mock_stream.close.assert_called_once()

    def test_close_clears_recording_state(self):
        """close() should clear recording state and active frames."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.open()
            capture.set_recording(True)
            capture._active_frames.append(np.array([1.0, 2.0]))
            capture.close()

            assert not capture._recording
            assert len(capture._active_frames) == 0

    def test_close_without_open_is_safe(self):
        """close() without prior open() should not raise."""
        capture = AudioCapture()
        capture.close()  # Should not raise


class TestRingBuffer:
    """Tests for ring buffer functionality."""

    def test_ring_buffer_stores_audio(self):
        """Ring buffer should store incoming audio."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=100)
        
        # Simulate callback with audio data
        audio = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 5, None, None)

        # Retrieve from ring buffer
        result = capture.get_pre_roll(0.05)  # 5 samples at 100 Hz
        np.testing.assert_array_almost_equal(result, audio)

    def test_ring_buffer_wraps_correctly(self):
        """Ring buffer should wrap around when full."""
        capture = AudioCapture(ring_buffer_seconds=0.1, sample_rate=100)
        # Buffer size = 10 samples

        # Write 15 samples (should wrap)
        audio1 = np.arange(10, dtype=np.float32)
        audio2 = np.array([10, 11, 12, 13, 14], dtype=np.float32)
        
        capture._audio_callback(audio1.reshape(-1, 1), 10, None, None)
        capture._audio_callback(audio2.reshape(-1, 1), 5, None, None)

        # Get last 10 samples (full buffer)
        result = capture.get_pre_roll(0.1)
        expected = np.array([5, 6, 7, 8, 9, 10, 11, 12, 13, 14], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_ring_buffer_partial_retrieval(self):
        """get_pre_roll should return only requested seconds."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=100)
        
        audio = np.arange(50, dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 50, None, None)

        # Request only last 20 samples (0.2s)
        result = capture.get_pre_roll(0.2)
        expected = np.arange(30, 50, dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_ring_buffer_empty_request(self):
        """Requesting 0 seconds should return empty array."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=100)
        result = capture.get_pre_roll(0.0)
        assert len(result) == 0

    def test_ring_buffer_oversized_audio_chunk(self):
        """Audio chunk larger than buffer should take last portion."""
        capture = AudioCapture(ring_buffer_seconds=0.1, sample_rate=100)
        # Buffer size = 10 samples
        
        # Write 20 samples (larger than buffer)
        audio = np.arange(20, dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 20, None, None)
        
        result = capture.get_pre_roll(0.1)
        expected = np.arange(10, 20, dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)


class TestRecordingControl:
    """Tests for set_recording and active buffer."""

    def test_set_recording_enables_capture(self):
        """set_recording(True) should enable active buffer capture."""
        capture = AudioCapture(sample_rate=100)
        capture.set_recording(True)

        audio = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 3, None, None)

        result = capture.drain_frames()
        np.testing.assert_array_almost_equal(result, audio)

    def test_set_recording_disables_capture(self):
        """set_recording(False) should stop active buffer capture."""
        capture = AudioCapture(sample_rate=100)
        capture.set_recording(True)

        audio1 = np.array([1.0, 2.0], dtype=np.float32)
        capture._audio_callback(audio1.reshape(-1, 1), 2, None, None)
        
        capture.set_recording(False)
        
        audio2 = np.array([3.0, 4.0], dtype=np.float32)
        capture._audio_callback(audio2.reshape(-1, 1), 2, None, None)

        result = capture.drain_frames()
        np.testing.assert_array_almost_equal(result, audio1)

    def test_set_recording_clears_on_enable(self):
        """set_recording(True) should clear previous active frames."""
        capture = AudioCapture(sample_rate=100)
        capture._active_frames.append(np.array([9.9, 9.9]))
        
        capture.set_recording(True)
        
        audio = np.array([1.0, 2.0], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 2, None, None)
        
        result = capture.drain_frames()
        np.testing.assert_array_almost_equal(result, audio)

    def test_ring_buffer_receives_audio_when_not_recording(self):
        """Ring buffer should always receive audio, even when not recording."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=100)
        
        # Not recording
        assert not capture._recording
        
        audio = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 3, None, None)
        
        result = capture.get_pre_roll(0.03)
        np.testing.assert_array_almost_equal(result, audio)


class TestDrainFrames:
    """Tests for drain_frames()."""

    def test_drain_frames_returns_audio(self):
        """drain_frames() should return accumulated audio."""
        capture = AudioCapture(sample_rate=100)
        capture.set_recording(True)

        audio1 = np.array([1.0, 2.0], dtype=np.float32)
        audio2 = np.array([3.0, 4.0, 5.0], dtype=np.float32)
        capture._audio_callback(audio1.reshape(-1, 1), 2, None, None)
        capture._audio_callback(audio2.reshape(-1, 1), 3, None, None)

        result = capture.drain_frames()
        expected = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_drain_frames_clears_buffer(self):
        """drain_frames() should clear the active buffer."""
        capture = AudioCapture(sample_rate=100)
        capture.set_recording(True)

        audio = np.array([1.0, 2.0], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 2, None, None)

        capture.drain_frames()
        result = capture.drain_frames()
        
        assert len(result) == 0

    def test_drain_frames_empty_buffer(self):
        """drain_frames() on empty buffer should return empty array."""
        capture = AudioCapture()
        result = capture.drain_frames()
        assert len(result) == 0
        assert result.dtype == np.float32


class TestGetPreRoll:
    """Tests for get_pre_roll()."""

    def test_get_pre_roll_returns_recent_audio(self):
        """get_pre_roll() should return most recent audio."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=100)
        
        audio = np.arange(20, dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 20, None, None)
        
        result = capture.get_pre_roll(0.1)  # Last 10 samples
        expected = np.arange(10, 20, dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_get_pre_roll_with_wraparound(self):
        """get_pre_roll() should handle ring buffer wraparound."""
        capture = AudioCapture(ring_buffer_seconds=0.1, sample_rate=100)
        # Buffer size = 10 samples

        # Fill buffer to position 7
        audio1 = np.arange(7, dtype=np.float32)
        capture._audio_callback(audio1.reshape(-1, 1), 7, None, None)
        
        # Write 5 more (wraps around)
        audio2 = np.array([10, 11, 12, 13, 14], dtype=np.float32)
        capture._audio_callback(audio2.reshape(-1, 1), 5, None, None)
        
        # Get last 8 samples
        result = capture.get_pre_roll(0.08)
        expected = np.array([4, 5, 6, 10, 11, 12, 13, 14], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_get_pre_roll_exceeds_buffer_size(self):
        """Requesting more than buffer size should return full buffer."""
        capture = AudioCapture(ring_buffer_seconds=0.1, sample_rate=100)
        
        audio = np.arange(10, dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 10, None, None)
        
        # Request 2 seconds (but buffer only holds 0.1s)
        result = capture.get_pre_roll(2.0)
        np.testing.assert_array_almost_equal(result, audio)


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_write_and_read(self):
        """Concurrent writes to ring buffer and reads should be safe."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=1000)
        errors = []
        stop_event = threading.Event()

        def writer():
            for i in range(100):
                if stop_event.is_set():
                    break
                try:
                    audio = np.random.randn(100).astype(np.float32)
                    capture._audio_callback(audio.reshape(-1, 1), 100, None, None)
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        def reader():
            for i in range(100):
                if stop_event.is_set():
                    break
                try:
                    capture.get_pre_roll(0.05)
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        stop_event.set()
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"

    def test_concurrent_recording_toggle(self):
        """Toggling recording while audio is flowing should be safe."""
        capture = AudioCapture(ring_buffer_seconds=1.0, sample_rate=1000)
        errors = []

        def writer():
            for i in range(50):
                try:
                    audio = np.random.randn(100).astype(np.float32)
                    capture._audio_callback(audio.reshape(-1, 1), 100, None, None)
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        def toggler():
            for i in range(50):
                try:
                    capture.set_recording(i % 2 == 0)
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        def drainer():
            for i in range(50):
                try:
                    capture.drain_frames()
                    time.sleep(0.002)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=toggler),
            threading.Thread(target=drainer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"


class TestBackwardCompatibility:
    """Tests for backward compatible start()/stop() methods."""

    def test_start_opens_stream(self):
        """start() should open stream and begin recording."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.start()

            mock_sd.InputStream.assert_called_once()
            assert capture._recording

    def test_stop_returns_audio_and_closes(self):
        """stop() should return audio and close stream."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.start()
            
            # Simulate some audio
            capture._active_frames.append(np.array([1.0, 2.0], dtype=np.float32))
            
            result = capture.stop()

            np.testing.assert_array_almost_equal(result, np.array([1.0, 2.0]))
            mock_stream.stop.assert_called_once()
            mock_stream.close.assert_called_once()

    def test_stop_clears_active_frames(self):
        """stop() should clear active frames."""
        with patch("chirp.audio_capture.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            capture = AudioCapture()
            capture.start()
            capture._active_frames.append(np.array([1.0, 2.0]))
            capture.stop()

            assert len(capture._active_frames) == 0

    def test_stop_without_start_returns_empty(self):
        """stop() without start() should return empty array."""
        capture = AudioCapture()
        result = capture.stop()
        assert len(result) == 0


class TestStatusCallback:
    """Tests for status callback functionality."""

    def test_status_callback_invoked_on_status(self):
        """Status callback should be invoked when stream reports status."""
        callback = MagicMock()
        capture = AudioCapture(status_callback=callback)

        audio = np.array([1.0, 2.0], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 2, None, "input overflow")

        callback.assert_called_once_with("input overflow")

    def test_no_callback_when_no_status(self):
        """Status callback should not be invoked when status is None."""
        callback = MagicMock()
        capture = AudioCapture(status_callback=callback)

        audio = np.array([1.0, 2.0], dtype=np.float32)
        capture._audio_callback(audio.reshape(-1, 1), 2, None, None)

        callback.assert_not_called()

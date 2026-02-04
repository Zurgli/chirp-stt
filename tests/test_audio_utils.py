"""Tests for audio_utils module."""

from __future__ import annotations

import numpy as np
import pytest

from chirp.audio_utils import trim_silence


class TestTrimSilence:
    """Tests for trim_silence function."""

    def test_trim_silence_removes_leading_silence(self):
        """Leading silence should be removed."""
        sample_rate = 16000
        # 0.5s silence + 0.2s audio
        silence = np.zeros(int(0.5 * sample_rate), dtype=np.float32)
        audio = np.random.uniform(-0.5, 0.5, int(0.2 * sample_rate)).astype(np.float32)
        combined = np.concatenate([silence, audio])

        result = trim_silence(combined, threshold=0.01, sample_rate=sample_rate)

        # Result should be shorter than original (leading silence removed)
        assert len(result) < len(combined)
        # Result should start with non-silent audio
        window_size = int(sample_rate * 0.01)
        first_window_rms = np.sqrt(np.mean(result[:window_size] ** 2))
        assert first_window_rms > 0.01

    def test_trim_silence_removes_trailing_silence(self):
        """Trailing silence should be removed."""
        sample_rate = 16000
        # 0.2s audio + 0.5s silence
        audio = np.random.uniform(-0.5, 0.5, int(0.2 * sample_rate)).astype(np.float32)
        silence = np.zeros(int(0.5 * sample_rate), dtype=np.float32)
        combined = np.concatenate([audio, silence])

        result = trim_silence(combined, threshold=0.01, sample_rate=sample_rate)

        # Result should be shorter than original (trailing silence removed)
        assert len(result) < len(combined)
        # Result should end with non-silent audio
        window_size = int(sample_rate * 0.01)
        last_window_rms = np.sqrt(np.mean(result[-window_size:] ** 2))
        assert last_window_rms > 0.01

    def test_trim_silence_preserves_min_duration(self):
        """Trimmed audio should preserve minimum duration."""
        sample_rate = 16000
        min_duration = 0.1  # 100ms minimum
        min_samples = int(min_duration * sample_rate)

        # 0.3s silence + very short audio (10ms) + 0.3s silence
        silence1 = np.zeros(int(0.3 * sample_rate), dtype=np.float32)
        short_audio = np.random.uniform(-0.5, 0.5, int(0.01 * sample_rate)).astype(
            np.float32
        )
        silence2 = np.zeros(int(0.3 * sample_rate), dtype=np.float32)
        combined = np.concatenate([silence1, short_audio, silence2])

        result = trim_silence(
            combined, threshold=0.01, min_duration=min_duration, sample_rate=sample_rate
        )

        # Result should be at least min_duration
        assert len(result) >= min_samples

    def test_trim_silence_no_change_when_no_silence(self):
        """Audio without silence should remain unchanged or nearly so."""
        sample_rate = 16000
        # Pure audio, no silence
        audio = np.random.uniform(-0.5, 0.5, int(0.5 * sample_rate)).astype(np.float32)

        result = trim_silence(audio, threshold=0.01, sample_rate=sample_rate)

        # Result should be approximately the same length (within a window or two)
        window_size = int(sample_rate * 0.01)
        assert abs(len(result) - len(audio)) <= window_size

    def test_trim_silence_all_silent_returns_min_duration(self):
        """All-silent audio should return min_duration from center."""
        sample_rate = 16000
        min_duration = 0.1
        min_samples = int(min_duration * sample_rate)

        # 1 second of silence
        silence = np.zeros(int(1.0 * sample_rate), dtype=np.float32)

        result = trim_silence(
            silence, threshold=0.01, min_duration=min_duration, sample_rate=sample_rate
        )

        # Result should be exactly min_duration samples
        assert len(result) == min_samples

    def test_trim_silence_empty_input(self):
        """Empty input should return empty array."""
        empty = np.array([], dtype=np.float32)

        result = trim_silence(empty)

        assert len(result) == 0
        assert result.dtype == np.float32

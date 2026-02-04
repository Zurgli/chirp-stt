"""Audio utility functions for processing audio data."""

from __future__ import annotations

import numpy as np


def trim_silence(
    audio: np.ndarray,
    threshold: float = 0.01,
    min_duration: float = 0.1,
    sample_rate: int = 16000,
) -> np.ndarray:
    """
    Trim leading and trailing silence from audio.

    Args:
        audio: Audio samples as numpy array
        threshold: RMS energy threshold (0.01 default)
        min_duration: Minimum duration to preserve in seconds
        sample_rate: Audio sample rate

    Returns:
        Trimmed audio, or original if all silent or no trimming needed
    """
    if len(audio) == 0:
        return audio

    min_samples = int(min_duration * sample_rate)

    # Compute RMS energy in 10ms windows
    window_samples = int(sample_rate * 0.01)  # 10ms windows

    if window_samples == 0:
        window_samples = 1

    # Pad audio to make it evenly divisible by window size
    num_windows = int(np.ceil(len(audio) / window_samples))
    padded_length = num_windows * window_samples
    padded_audio = np.zeros(padded_length, dtype=audio.dtype)
    padded_audio[: len(audio)] = audio

    # Reshape and compute RMS per window
    windows = padded_audio.reshape(num_windows, window_samples)
    rms_per_window = np.sqrt(np.mean(windows**2, axis=1))

    # Find windows above threshold
    above_threshold = rms_per_window > threshold

    if not np.any(above_threshold):
        # All silent - return minimum duration from center
        center = len(audio) // 2
        half_min = min_samples // 2
        start = max(0, center - half_min)
        end = min(len(audio), start + min_samples)
        # Adjust start if end hit the boundary
        if end - start < min_samples:
            start = max(0, end - min_samples)
        return audio[start:end]

    # Find first and last window above threshold
    first_window = np.argmax(above_threshold)
    last_window = len(above_threshold) - 1 - np.argmax(above_threshold[::-1])

    # Convert window indices to sample indices
    start_sample = first_window * window_samples
    end_sample = min((last_window + 1) * window_samples, len(audio))

    # Ensure minimum duration
    current_duration = end_sample - start_sample
    if current_duration < min_samples:
        # Expand symmetrically to meet minimum duration
        needed = min_samples - current_duration
        expand_start = needed // 2
        expand_end = needed - expand_start

        start_sample = max(0, start_sample - expand_start)
        end_sample = min(len(audio), end_sample + expand_end)

        # If we hit a boundary, expand the other direction
        current_duration = end_sample - start_sample
        if current_duration < min_samples:
            if start_sample == 0:
                end_sample = min(len(audio), min_samples)
            else:
                start_sample = max(0, end_sample - min_samples)

    return audio[start_sample:end_sample]

import unittest

from chirp.config_manager import ChirpConfig


class TestConfigValidation(unittest.TestCase):
    def test_validate_threads_negative(self):
        """Negative threads should fail validation."""
        conf = ChirpConfig(threads=-1)
        with self.assertRaisesRegex(ValueError, "threads must be non-negative"):
            conf.validate()

    def test_validate_clipboard_delay_negative(self):
        """Non-positive clipboard_clear_delay should fail validation."""
        conf = ChirpConfig(clipboard_clear_delay=-1.0)
        with self.assertRaisesRegex(ValueError, "clipboard_clear_delay must be positive"):
            conf.validate()

    def test_validate_clipboard_delay_zero(self):
        """Zero clipboard_clear_delay should fail validation."""
        conf = ChirpConfig(clipboard_clear_delay=0)
        with self.assertRaisesRegex(ValueError, "clipboard_clear_delay must be positive"):
            conf.validate()

    def test_validate_paste_mode_invalid(self):
        """Invalid paste_mode should fail validation."""
        conf = ChirpConfig(paste_mode="hacking")
        with self.assertRaisesRegex(ValueError, r"paste_mode must be 'ctrl' or 'ctrl\+shift'"):
            conf.validate()

    def test_validate_model_timeout_negative(self):
        """Negative model_timeout should fail validation."""
        conf = ChirpConfig(model_timeout=-1.0)
        with self.assertRaisesRegex(ValueError, "model_timeout must be non-negative"):
            conf.validate()

    def test_validate_max_recording_duration_negative(self):
        """Negative max_recording_duration should fail validation."""
        conf = ChirpConfig(max_recording_duration=-1.0)
        with self.assertRaisesRegex(ValueError, "max_recording_duration must be non-negative"):
            conf.validate()

    def test_validate_max_recording_duration_excessive(self):
        """Excessive max_recording_duration should fail validation (DoS prevention)."""
        conf = ChirpConfig(max_recording_duration=7201.0)
        with self.assertRaisesRegex(ValueError, "max_recording_duration must be <="):
            conf.validate()

    def test_validate_sound_path_missing(self):
        """Non-existent sound paths should fail validation."""
        conf = ChirpConfig(start_sound_path="/this/path/absolutely/should/not/exist.wav")
        with self.assertRaisesRegex(ValueError, "start_sound_path does not exist"):
            conf.validate()

        conf = ChirpConfig(stop_sound_path="/this/path/absolutely/should/not/exist.wav")
        with self.assertRaisesRegex(ValueError, "stop_sound_path does not exist"):
            conf.validate()

    def test_validate_audio_feedback_volume_below_zero(self):
        """Negative audio_feedback_volume should fail validation."""
        conf = ChirpConfig(audio_feedback_volume=-0.1)
        with self.assertRaisesRegex(ValueError, "audio_feedback_volume must be between 0.0 and 1.0"):
            conf.validate()

    def test_validate_audio_feedback_volume_above_one(self):
        """audio_feedback_volume above 1.0 should fail validation."""
        conf = ChirpConfig(audio_feedback_volume=1.5)
        with self.assertRaisesRegex(ValueError, "audio_feedback_volume must be between 0.0 and 1.0"):
            conf.validate()

    def test_validate_audio_feedback_volume_valid_range(self):
        """audio_feedback_volume within 0.0-1.0 should pass validation."""
        for vol in [0.0, 0.5, 1.0]:
            conf = ChirpConfig(audio_feedback_volume=vol)
            conf.validate()  # Should not raise

    # --- Streaming/chunked transcription field tests ---

    def test_streaming_fields_have_correct_defaults(self):
        """All new streaming fields should have correct default values."""
        conf = ChirpConfig()
        self.assertEqual(conf.streaming_transcription, True)
        self.assertEqual(conf.chunk_duration, 4.0)
        self.assertEqual(conf.chunk_overlap, 0.5)
        self.assertEqual(conf.pre_roll_seconds, 0.2)
        self.assertEqual(conf.ring_buffer_seconds, 10.0)
        self.assertEqual(conf.merge_window_words, 5)
        self.assertEqual(conf.max_chunk_queue_depth, 3)
        self.assertEqual(conf.silence_threshold, 0.01)

    def test_validate_chunk_duration_too_small(self):
        """chunk_duration < 1.0 should fail validation."""
        conf = ChirpConfig(chunk_duration=0.5)
        with self.assertRaisesRegex(ValueError, "chunk_duration must be >= 1.0"):
            conf.validate()

    def test_validate_chunk_overlap_negative(self):
        """Negative chunk_overlap should fail validation."""
        conf = ChirpConfig(chunk_overlap=-0.1)
        with self.assertRaisesRegex(ValueError, "chunk_overlap must be >= 0"):
            conf.validate()

    def test_validate_chunk_duration_not_greater_than_overlap(self):
        """chunk_duration must be > chunk_overlap."""
        # Equal case
        conf = ChirpConfig(chunk_duration=2.0, chunk_overlap=2.0)
        with self.assertRaisesRegex(ValueError, "chunk_duration must be > chunk_overlap"):
            conf.validate()

        # Overlap greater
        conf = ChirpConfig(chunk_duration=2.0, chunk_overlap=3.0)
        with self.assertRaisesRegex(ValueError, "chunk_duration must be > chunk_overlap"):
            conf.validate()

    def test_validate_ring_buffer_too_small(self):
        """ring_buffer_seconds must be >= chunk_duration + pre_roll_seconds."""
        # chunk_duration=4.0, pre_roll_seconds=0.2 -> need at least 4.2
        conf = ChirpConfig(ring_buffer_seconds=4.0)
        with self.assertRaisesRegex(ValueError, "ring_buffer_seconds must be >= chunk_duration"):
            conf.validate()

    def test_validate_merge_window_words_zero(self):
        """merge_window_words < 1 should fail validation."""
        conf = ChirpConfig(merge_window_words=0)
        with self.assertRaisesRegex(ValueError, "merge_window_words must be >= 1"):
            conf.validate()

    def test_validate_max_chunk_queue_depth_zero(self):
        """max_chunk_queue_depth < 1 should fail validation."""
        conf = ChirpConfig(max_chunk_queue_depth=0)
        with self.assertRaisesRegex(ValueError, "max_chunk_queue_depth must be >= 1"):
            conf.validate()

    def test_validate_silence_threshold_negative(self):
        """Negative silence_threshold should fail validation."""
        conf = ChirpConfig(silence_threshold=-0.01)
        with self.assertRaisesRegex(ValueError, "silence_threshold must be >= 0"):
            conf.validate()

    def test_validate_streaming_fields_valid_config(self):
        """Valid streaming config should pass validation."""
        conf = ChirpConfig(
            chunk_duration=3.0,
            chunk_overlap=0.5,
            pre_roll_seconds=0.5,
            ring_buffer_seconds=5.0,
            merge_window_words=3,
            max_chunk_queue_depth=2,
            silence_threshold=0.0,
        )
        conf.validate()  # Should not raise

    def test_validate_streaming_edge_cases(self):
        """Edge cases for streaming validation."""
        # Minimum valid ring_buffer (exactly chunk_duration + pre_roll_seconds)
        conf = ChirpConfig(
            chunk_duration=2.0,
            pre_roll_seconds=0.5,
            ring_buffer_seconds=2.5,
        )
        conf.validate()  # Should not raise

        # Zero overlap is valid
        conf = ChirpConfig(chunk_overlap=0.0)
        conf.validate()  # Should not raise

        # Zero silence_threshold is valid
        conf = ChirpConfig(silence_threshold=0.0)
        conf.validate()  # Should not raise

    def test_valid_default_config(self):
        """Default config should pass validation."""
        conf = ChirpConfig()
        conf.validate()  # Should not raise

    def test_valid_config_with_zero_timeouts(self):
        """Zero timeouts (disable) should pass validation."""
        conf = ChirpConfig(model_timeout=0, max_recording_duration=0)
        conf.validate()  # Should not raise

    def test_from_dict_then_validate(self):
        """Verify the flow used by ConfigManager (from_dict -> validate)."""
        data = {"threads": -5, "paste_mode": "Hack"}
        conf = ChirpConfig.from_dict(data)
        # from_dict converts "Hack" to "hack"
        self.assertEqual(conf.paste_mode, "hack")

        with self.assertRaisesRegex(ValueError, "threads must be non-negative"):
            conf.validate()

        conf.threads = 1  # fix threads
        with self.assertRaisesRegex(ValueError, r"paste_mode must be 'ctrl' or 'ctrl\+shift'"):
            conf.validate()


if __name__ == "__main__":
    unittest.main()

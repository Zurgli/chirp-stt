# Chunked Transcription Tasks

**Design doc:** `docs/plans/2026-02-03-chunked-background-transcription-design.md`
**Spec:** `docs/specs/chunked-transcription.md`

---

## CT-01: Add silence trimming utility

**Status:** done

**Description:**
Create the `trim_silence()` function that removes leading and trailing silence from audio chunks. This reduces wasted inference time and improves merge accuracy by producing cleaner chunk boundaries.

**Files:**
- Create `src/chirp/audio_utils.py`

**Implementation:**
- Compute RMS energy in 10ms windows
- Find first/last window exceeding threshold
- Return trimmed slice, ensuring minimum duration
- Handle edge cases: all-silent audio, no-silence audio

**Acceptance criteria:**
- [ ] `trim_silence(audio, threshold, min_duration, sample_rate)` function exists
- [ ] Returns trimmed audio when silence detected at boundaries
- [ ] Preserves at least `min_duration` seconds of audio
- [ ] Returns original audio if no trimming needed
- [ ] Handles all-silent input without crashing
- [ ] Unit tests pass: `uv run pytest tests/test_audio_utils.py -v`

**Spec reference:** See "Silence Trimming" section

---

## CT-02: Add merge algorithm for chunk transcripts

**Status:** done

**Description:**
Implement the word-overlap merge algorithm that combines sequential chunk transcripts while removing duplicates caused by audio overlap.

**Files:**
- Create `src/chirp/text_merge.py`

**Implementation:**
- Tokenize on whitespace, strip punctuation for comparison only
- Compare last N words of accumulated text with first N words of new chunk
- Find longest suffix↔prefix match (case-insensitive)
- Drop matched prefix from new chunk, append remainder
- Handle empty chunks, single-word chunks, divergent transcriptions

**Acceptance criteria:**
- [ ] `merge_transcripts(accumulated: str, new_chunk: str, window: int) -> str` function exists
- [ ] Correctly handles perfect overlap (identical words)
- [ ] Correctly handles partial overlap (subset match)
- [ ] Correctly handles no overlap (clean append with space)
- [ ] Preserves original punctuation in output
- [ ] Skips empty/whitespace-only chunks
- [ ] Unit tests pass: `uv run pytest tests/test_text_merge.py -v`

**Spec reference:** See "Merge Algorithm" section

---

## CT-03: Create ChunkedTranscriber core class

**Status:** done

**Description:**
Create the chunking controller that buffers audio frames, creates chunks at the right intervals, manages the worker thread/queue, and orchestrates transcription.

**Dependencies:** CT-01, CT-02

**Files:**
- Create `src/chirp/chunked_transcriber.py`

**Implementation:**
- Constructor accepts `transcribe_fn`, chunk settings, queue settings
- `start(pre_roll)` initializes state for new session
- `feed(frames)` accumulates audio, creates chunks when buffer exceeds duration
- Worker thread processes queue, stores results in order
- Apply silence trimming before enqueuing
- Track dropped chunks for fallback detection
- `shutdown()` for clean thread termination

**Acceptance criteria:**
- [ ] `ChunkedTranscriber` class with `start()`, `feed()`, `shutdown()` methods
- [ ] Creates chunks of correct duration with specified overlap
- [ ] Worker thread processes chunks sequentially
- [ ] Silence trimming applied to each chunk before transcription
- [ ] Chunks stored in order for later merge
- [ ] Queue overflow handled: drop chunk, increment counter, log warning
- [ ] Thread shuts down cleanly on `shutdown()`
- [ ] Unit tests pass: `uv run pytest tests/test_chunked_transcriber.py -v`

**Spec reference:** See "ChunkedTranscriber" and "Data Flow" sections

---

## CT-04: Add finalize method to ChunkedTranscriber

**Status:** done

**Description:**
Implement the finalization logic that processes remaining audio, waits for the worker to complete, and merges all chunk transcripts into final text.

**Dependencies:** CT-03

**Files:**
- Modify `src/chirp/chunked_transcriber.py`

**Implementation:**
- `finalize(timeout)` enqueues tail audio as final chunk
- Wait for worker to drain queue (with timeout)
- Merge all chunk transcripts using merge algorithm
- Return final text
- Log warning on timeout, return partial results
- Detect if fallback needed (chunks dropped)

**Acceptance criteria:**
- [ ] `finalize(timeout: Optional[float]) -> str` method exists
- [ ] Enqueues remaining audio as tail chunk
- [ ] Waits for queue to drain within timeout
- [ ] Returns merged text from all chunks
- [ ] Returns partial results on timeout (with warning log)
- [ ] Reports whether fallback is needed via return value or property
- [ ] Unit tests pass: `uv run pytest tests/test_chunked_transcriber.py::test_finalize -v`

**Spec reference:** See "Recording Stop" in Data Flow, "Finalization Timeout" in Error Handling

---

## CT-05: Refactor AudioCapture for persistent stream

**Status:** done

**Description:**
Modify `AudioCapture` to maintain a persistent `InputStream` with ring buffer, eliminating the device initialization delay on each recording toggle.

**Files:**
- Modify `src/chirp/audio_capture.py`

**Implementation:**
- Add `open()` to start persistent stream at app startup
- Add `close()` to stop stream at app shutdown
- Add ring buffer (circular, stores last N seconds)
- Add `set_recording(active)` to toggle active buffer accumulation
- Add `drain_frames()` to retrieve and clear active buffer
- Add `get_pre_roll(seconds)` to retrieve recent audio from ring buffer
- Callback always writes to ring buffer; writes to active buffer only when recording
- Preserve existing `start()`/`stop()` for backward compatibility (call open/close internally)

**Acceptance criteria:**
- [ ] `open()` and `close()` methods exist and manage stream lifecycle
- [ ] Ring buffer stores last `ring_buffer_seconds` of audio
- [ ] `set_recording(True/False)` controls active buffer accumulation
- [ ] `drain_frames()` returns and clears active buffer contents
- [ ] `get_pre_roll(seconds)` returns recent audio from ring buffer
- [ ] Existing `start()`/`stop()` still work (backward compatible)
- [ ] Thread-safe ring buffer operations
- [ ] Unit tests pass: `uv run pytest tests/test_audio_capture.py -v`

**Spec reference:** See "AudioCapture (refactored)" section

---

## CT-06: Add device error recovery to AudioCapture

**Status:** done

**Description:**
Add error handling for audio device issues (unplug, sleep/resume) with automatic recovery attempts.

**Dependencies:** CT-05

**Files:**
- Modify `src/chirp/audio_capture.py`

**Implementation:**
- Catch `sd.PortAudioError` in callback and stream operations
- Log warning with error details
- Attempt to close and reopen stream
- Notify via status callback if recovery fails
- Track error state for ChirpApp to query

**Acceptance criteria:**
- [ ] `PortAudioError` caught and logged (not propagated)
- [ ] Automatic stream recovery attempted
- [ ] Status callback notified of device errors
- [ ] Error state queryable (`has_device_error` property or similar)
- [ ] Graceful degradation when recovery fails
- [ ] Tests pass: `uv run pytest tests/test_audio_capture.py::test_device_error -v`

**Spec reference:** See "Device Errors" in Error Handling

---

## CT-07: Add ring buffer tests

**Status:** done

**Description:**
Create comprehensive tests for the ring buffer implementation in AudioCapture.

**Dependencies:** CT-05

**Files:**
- Add tests to `tests/test_audio_capture.py` or create `tests/test_ring_buffer.py`

**Test cases:**
- Buffer wrapping (write more than capacity, verify oldest discarded)
- Pre-roll retrieval accuracy (request N seconds, get exactly N seconds)
- Concurrent read/write safety (simulate callback + main thread access)
- Edge cases: request more than available, empty buffer, exact capacity

**Acceptance criteria:**
- [ ] Test: buffer wrapping discards oldest data correctly
- [ ] Test: pre-roll returns correct duration of audio
- [ ] Test: concurrent access doesn't corrupt data or deadlock
- [ ] Test: edge cases handled gracefully
- [ ] All tests pass: `uv run pytest tests/test_audio_capture.py -v`

**Spec reference:** See "Ring Buffer Tests" in Testing Strategy

---

## CT-08: Wire chunked transcription in ChirpApp

**Status:** done

**Description:**
Integrate `ChunkedTranscriber` and refactored `AudioCapture` into the main application flow.

**Dependencies:** CT-04, CT-05

**Files:**
- Modify `src/chirp/main.py`

**Implementation:**
- Initialize `AudioCapture.open()` at startup, `close()` on shutdown
- Create `ChunkedTranscriber` instance with `ParakeetManager.transcribe`
- On recording start: clear buffers, get pre-roll, enable recording, start chunking
- Periodically feed frames to transcriber (timer or thread)
- On recording stop: disable recording, finalize, inject text
- Add `_finalization_in_progress` flag for rapid toggle blocking
- Keep fallback to full-utterance when `streaming_transcription = false`

**Acceptance criteria:**
- [ ] Audio stream opened at startup, closed on shutdown
- [ ] Pre-roll captured on recording start
- [ ] Chunks fed to transcriber during recording
- [ ] Finalization produces merged text on recording stop
- [ ] Text injected via existing TextInjector flow
- [ ] Rapid toggle blocked during finalization
- [ ] Fallback to full-utterance when streaming disabled
- [ ] Manual testing: record 15s clip, verify <1s stop-to-text latency

**Spec reference:** See "Data Flow" section

---

## CT-09: Handle model timeout interaction

**Status:** done

**Description:**
When streaming transcription is enabled, disable model unloading to keep the model warm for instant chunk processing.

**Dependencies:** CT-08

**Files:**
- Modify `src/chirp/main.py`
- Update `config.toml` comments

**Implementation:**
- When `streaming_transcription = true`, set `model_timeout = 0` internally
- Override config file value (log debug message about override)
- Document behavior in config.toml comments

**Acceptance criteria:**
- [ ] Model never unloads when `streaming_transcription = true`
- [ ] Config file `model_timeout` value ignored when streaming enabled
- [ ] Debug log indicates model_timeout override
- [ ] Config.toml documents this behavior in comments
- [ ] Tests pass: `uv run pytest tests/test_main.py -v`

**Spec reference:** See "Model Timeout Interaction" section

---

## CT-10: Add new config fields and validation

**Status:** done

**Description:**
Add all new configuration fields to `ChirpConfig` with proper validation rules.

**Files:**
- Modify `src/chirp/config_manager.py`
- Update `config.toml`

**New fields:**
- `streaming_transcription: bool = True`
- `chunk_duration: float = 4.0`
- `chunk_overlap: float = 0.5`
- `pre_roll_seconds: float = 0.2`
- `ring_buffer_seconds: float = 10.0`
- `merge_window_words: int = 5`
- `max_chunk_queue_depth: int = 3`
- `silence_threshold: float = 0.01`

**Validation:**
- `chunk_duration > chunk_overlap >= 0`
- `chunk_duration >= 1.0`
- `ring_buffer_seconds >= chunk_duration + pre_roll_seconds`
- `merge_window_words >= 1`
- `max_chunk_queue_depth >= 1`
- `silence_threshold >= 0`

**Acceptance criteria:**
- [ ] All new fields added to `ChirpConfig` dataclass
- [ ] Default values match spec
- [ ] Validation rules enforced in `validate()` method
- [ ] Config.toml updated with commented examples
- [ ] Invalid configs raise `ValueError` with clear message
- [ ] Tests pass: `uv run pytest tests/test_config_manager.py -v`

**Spec reference:** See "Configuration" section

---

## CT-11: Add merge logic tests

**Status:** done

**Description:**
Create comprehensive unit tests for the merge algorithm covering all edge cases.

**Dependencies:** CT-02

**Files:**
- Create `tests/test_text_merge.py`

**Test cases:**
- Perfect overlap: "hello world" + "world says hi" → "hello world says hi"
- Partial overlap: "the quick brown" + "brown fox jumps" → "the quick brown fox jumps"
- No overlap: "hello" + "world" → "hello world"
- Punctuation: "Hello." + "Hello, world" → "Hello. world" (or appropriate handling)
- Divergent: "I'll go" + "I will go there" → prefer earlier
- Empty chunk: "hello" + "" → "hello"
- Single word: "a" + "a b" → "a b"
- Case insensitive: "Hello" + "hello world" → "Hello world"

**Acceptance criteria:**
- [ ] All test cases above covered
- [ ] Tests are independent and fast
- [ ] Tests pass: `uv run pytest tests/test_text_merge.py -v`

**Spec reference:** See "Merge Algorithm" section

---

## CT-12: Add integration tests

**Status:** done

**Description:**
Create integration tests that verify the full chunked transcription flow works end-to-end.

**Dependencies:** CT-08

**Files:**
- Create `tests/test_chunked_integration.py`

**Test cases:**
- Full cycle: mock audio → chunk → transcribe → merge → verify output
- Rapid toggle: start → stop → start quickly, verify blocking behavior
- Queue overflow: slow transcriber, verify fallback to full-utterance
- Device error: mock PortAudioError, verify recovery attempt

**Acceptance criteria:**
- [ ] Full cycle test passes with mocked audio and transcriber
- [ ] Rapid toggle test verifies blocking behavior
- [ ] Queue overflow test verifies fallback
- [ ] Device error test verifies recovery attempt
- [ ] Tests pass: `uv run pytest tests/test_chunked_integration.py -v`

**Spec reference:** See "Integration Tests" in Testing Strategy

---

## CT-13: Add instrumentation and debug logging

**Status:** done

**Description:**
Add comprehensive debug logging throughout the chunked transcription pipeline for troubleshooting and performance analysis.

**Dependencies:** CT-08

**Files:**
- Modify `src/chirp/chunked_transcriber.py`
- Modify `src/chirp/audio_capture.py`

**Logged events:**
- Chunk created: duration (ms), silence trimmed (ms)
- Chunk enqueued: queue depth
- Chunk transcribed: transcription time (ms), text length
- Merge performed: overlap words found, words dropped
- Finalization complete: total time (ms), chunks processed, fallback used
- Device error: error type, recovery status

**Acceptance criteria:**
- [ ] All events listed above are logged at DEBUG level
- [ ] Log messages include relevant metrics
- [ ] Logs don't impact performance in non-debug mode
- [ ] Manual verification: enable debug logging, record clip, verify log output
- [ ] Tests pass: `uv run pytest -v`

**Spec reference:** See "Instrumentation" section

---

## Summary

| ID | Title | Status | Dependencies |
|----|-------|--------|--------------|
| CT-01 | Add silence trimming utility | pending | - |
| CT-02 | Add merge algorithm for chunk transcripts | pending | - |
| CT-03 | Create ChunkedTranscriber core class | pending | CT-01, CT-02 |
| CT-04 | Add finalize method to ChunkedTranscriber | pending | CT-03 |
| CT-05 | Refactor AudioCapture for persistent stream | pending | - |
| CT-06 | Add device error recovery to AudioCapture | pending | CT-05 |
| CT-07 | Add ring buffer tests | pending | CT-05 |
| CT-08 | Wire chunked transcription in ChirpApp | pending | CT-04, CT-05 |
| CT-09 | Handle model timeout interaction | pending | CT-08 |
| CT-10 | Add new config fields and validation | pending | - |
| CT-11 | Add merge logic tests | pending | CT-02 |
| CT-12 | Add integration tests | pending | CT-08 |
| CT-13 | Add instrumentation and debug logging | pending | CT-08 |

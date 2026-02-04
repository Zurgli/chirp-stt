# Chunked background transcription plan

## Summary

Chirp feels slow at two points: the hotkey → recording start delay (1–3s) and the stop → text delay (2–5s) on 15–30s clips. The fastest way to reduce the stop delay is to transcribe while recording. This plan adds chunked background transcription with overlap and a light merge step. The UI stays the same: the user still toggles recording and gets one final paste.

## Goals

- Cut stop → text latency to <1s on 15–30s clips.
- Reduce hotkey → recording start delay by keeping audio streaming warm.
- Keep accuracy close to the current full‑utterance path.
- Preserve a single final paste (no streaming text injection).

## Non‑goals

- True live streaming UI updates.
- Changing the STT backend or model.
- GPU support.

## Current behavior and bottlenecks

- `AudioCapture.start()` opens a new `sounddevice.InputStream` on every toggle. Device init can take hundreds of ms or more on Windows.
- `ParakeetManager.transcribe()` runs once on the entire waveform, so latency grows with clip length.
- Text injection uses `keyboard.write()` but is usually a small fraction of total time.
- `ParakeetManager` unloads the model after `model_timeout` (default 300s) of inactivity, which conflicts with keeping things warm.

## Proposed design

### 1) Keep the audio stream open

- Open the `InputStream` once at app startup.
- Maintain an in‑memory ring buffer of the last N seconds (default 10s, must be >= `chunk_duration + pre_roll_seconds`).
- When recording toggles on, start copying frames from the callback into an active buffer without reopening the stream.
- On device errors (unplug, sleep/resume), catch `sd.PortAudioError` and attempt to reopen the stream gracefully with a warning log.

### 2) Pre‑roll capture

- When recording starts, copy the last `pre_roll_seconds` (default 0.2s) from the ring buffer into the active buffer.
- This captures audio spoken slightly before the hotkey press, avoiding clipped word starts.
- Pre‑roll frames are prepended to the first chunk only.

### 3) Chunked transcription while recording

- Split audio into fixed‑size chunks (default 4s) with a short overlap (default 0.5s).
- Push each chunk into a `queue.Queue` for a single worker thread that calls `ParakeetManager.transcribe()` sequentially.
- Store each chunk's text output in order.
- **Queue overflow handling**: If queue depth exceeds `max_chunk_queue_depth` (default 3), log a warning and drop the newest chunk. On finalization, fall back to full‑utterance transcription if any chunks were dropped.

### 4) Merge chunk text safely

- Use a lightweight word‑overlap merge to remove duplicates caused by overlap.
- Algorithm:
  1. Tokenize on whitespace; strip punctuation from tokens for comparison only (preserve original punctuation in output).
  2. Compare the last `merge_window_words` (default 5) of the accumulated transcript with the first `merge_window_words` of the next chunk.
  3. Find the longest matching suffix↔prefix overlap (case‑insensitive, punctuation‑stripped).
  4. Drop the duplicate prefix from the new chunk and append the remainder.
  5. If no overlap is found, append with a single space.
- **Divergent transcriptions**: When the model produces different text for overlapping audio (e.g., "I'll" vs "I will"), prefer the version from the earlier chunk (already committed) and drop the conflicting prefix.
- **Empty chunks**: If a chunk transcribes to empty/whitespace (silence), skip it during merge.

### 5) Finalization on stop

- On stop, enqueue the remaining tail chunk (audio after the last full chunk) and wait for the worker to finish.
- **Finalization timeout**: Wait up to `chunk_duration * 2` for the worker to drain. If exceeded, log a warning and use partial results.
- Merge all chunk transcripts, then pass through existing `TextInjector.process()` before paste.
- Fall back to the old full‑utterance path when:
  - `streaming_transcription` is disabled, or
  - Any chunks were dropped due to queue overflow, or
  - The worker thread fails/times out.

### 6) Rapid toggle handling

- If user toggles on→off→on before finalization completes:
  - **Block the new recording** until finalization finishes (simple, predictable).
  - Log a debug message: "Waiting for previous transcription to complete."
  - This prevents audio loss and state corruption.

### 7) Model timeout interaction

- When `streaming_transcription = true`, **disable model unloading** to keep the model warm.
- Set `model_timeout = 0` internally when streaming is enabled, regardless of config file value.
- Document this behavior in config.toml comments.

### 8) Silence trimming (low‑effort optimization)

- Before transcribing each chunk, trim leading and trailing silence using a simple energy threshold.
- This reduces wasted inference on quiet sections and improves merge accuracy.
- Use RMS energy < 0.01 (configurable via `silence_threshold`) as the cutoff.
- Preserve at least 0.1s of audio to avoid empty chunks from brief pauses.

## Configuration additions

Add new `ChirpConfig` fields with sane defaults:

```toml
# Chunked transcription (streaming while recording)
streaming_transcription = true       # Enable chunked background transcription
chunk_duration = 4.0                 # Seconds per chunk
chunk_overlap = 0.5                  # Overlap between chunks for merge accuracy
pre_roll_seconds = 0.2               # Capture audio before hotkey press
ring_buffer_seconds = 10.0           # Ring buffer size (>= chunk_duration + pre_roll)
merge_window_words = 5               # Words to compare for overlap detection
max_chunk_queue_depth = 3            # Max pending chunks before fallback
silence_threshold = 0.01             # RMS threshold for silence trimming (0 to disable)
```

## Implementation plan

1) **Add a chunking controller**
   - New module: `src/chirp/chunked_transcriber.py`.
   - Responsibilities: buffer frames, build chunks, enqueue work, store chunk transcripts, merge on finalize.
   - Use one worker thread with a `queue.Queue` to serialize calls to `ParakeetManager`.
   - Implement `shutdown()` method for clean thread termination on app exit.

2) **Add silence trimming utility**
   - New function in `chunked_transcriber.py`: `trim_silence(audio, threshold, min_duration)`.
   - Returns trimmed audio or original if below min_duration.

3) **Refactor `AudioCapture` for a persistent stream**
   - Add `open()` and `close()` methods to manage a single `InputStream`.
   - Add `set_recording(active: bool)` and `drain_frames()` to capture frames without reopening devices.
   - Callback appends to a ring buffer plus an active buffer when recording.
   - Add `get_pre_roll(seconds)` to retrieve recent audio from ring buffer.
   - Wrap stream operations in try/except for `sd.PortAudioError`; attempt recovery on failure.

4) **Wire chunked transcription in `ChirpApp`**
   - Initialize `AudioCapture.open()` at startup; `close()` on shutdown.
   - On start: clear buffers, grab pre‑roll, enable recording, start chunking timer.
   - On stop: disable recording, finalize chunked transcription, then inject.
   - Add `_finalization_in_progress` flag to block rapid toggles.
   - Keep the current full‑utterance flow as a fallback when `streaming_transcription` is false.
   - Override `model_timeout = 0` when streaming is enabled.

5) **Add merge logic tests**
   - New unit tests: `tests/test_chunked_transcriber.py`.
   - Test cases:
     - Perfect overlap (identical words)
     - Partial overlap (subset match)
     - No overlap (clean append)
     - Punctuation at boundaries ("Hello." + "Hello, world")
     - Divergent transcriptions ("I'll" vs "I will")
     - Empty/silent chunks
     - Single‑word chunks

6) **Add ring buffer tests**
   - Test cases:
     - Buffer wrapping (overflow behavior)
     - Pre‑roll retrieval accuracy
     - Concurrent read/write safety

7) **Add integration tests**
   - Full cycle: record → chunk → merge → inject (mocked audio)
   - Rapid toggle handling
   - Queue overflow → fallback behavior
   - Device error recovery

8) **Expose new config fields and document defaults**
   - Update `config_manager.py` with new fields and validation:
     - `chunk_duration > chunk_overlap >= 0`
     - `chunk_duration >= 1.0` (minimum viable chunk)
     - `ring_buffer_seconds >= chunk_duration + pre_roll_seconds`
     - `merge_window_words >= 1`
     - `max_chunk_queue_depth >= 1`
   - Update `config.toml` with commented examples.

9) **Add instrumentation**
   - Log in debug mode:
     - Chunk durations and transcription times
     - Queue depth at enqueue
     - Merge decisions (overlap length, words dropped)
     - Finalization total time
     - Silence trimmed per chunk (ms)

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Duplicate or missing words at chunk boundaries | Overlap + merge heuristic with configurable window; fallback to full‑utterance on failure |
| CPU spikes from chunking | Single worker thread; queue depth limit with graceful degradation |
| Transcription slower than realtime | Queue overflow triggers fallback to full‑utterance |
| User‑perceived change | Keep single final paste and preserve existing hotkey flow |
| Device unplug / sleep‑resume | Catch PortAudioError and attempt stream recovery |
| Rapid toggle corruption | Block new recording until finalization completes |
| Model unload during recording | Disable model_timeout when streaming enabled |

## Success criteria

- Start latency <300ms after the first toggle (no device reopen).
- Stop → text latency <1s on 15–30s clips.
- No regression in word override, style, or paste behavior.
- Graceful degradation on queue overflow (fallback works, no crash).
- Clean recovery from device errors (warning logged, stream reopened).

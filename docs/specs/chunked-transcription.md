# Chunked Transcription Specification

## Overview

Chunked transcription enables background speech-to-text processing during recording. Instead of waiting until recording stops to transcribe the entire audio, the system processes fixed-size chunks in parallel with ongoing capture. This reduces stop-to-text latency from 2–5s to under 1s for typical 15–30s recordings.

## Goals

- Stop → text latency <1s on 15–30s clips
- Hotkey → recording start latency <300ms (after first toggle)
- Accuracy close to full-utterance path
- Single final paste (no streaming text injection)
- Graceful degradation on failure

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ChirpApp                                │
│  - Manages lifecycle (open/close stream, start/stop recording) │
│  - Coordinates AudioCapture ↔ ChunkedTranscriber               │
│  - Handles finalization and text injection                     │
└─────────────────────────────────────────────────────────────────┘
                    │                           │
                    ▼                           ▼
┌───────────────────────────────┐  ┌──────────────────────────────┐
│        AudioCapture           │  │     ChunkedTranscriber       │
│  - Persistent InputStream     │  │  - Chunk buffering           │
│  - Ring buffer (pre-roll)     │  │  - Worker thread + queue     │
│  - Active buffer (recording)  │  │  - Silence trimming          │
│  - get_pre_roll(seconds)      │  │  - Merge on finalize         │
└───────────────────────────────┘  └──────────────────────────────┘
                                              │
                                              ▼
                                   ┌──────────────────────────────┐
                                   │      ParakeetManager         │
                                   │  - Model loading/unloading   │
                                   │  - Transcription calls       │
                                   └──────────────────────────────┘
```

## Data Flow

### Recording Start

1. `ChirpApp.on_hotkey_press()` toggles recording on
2. `AudioCapture.get_pre_roll(pre_roll_seconds)` retrieves recent audio from ring buffer
3. Pre-roll audio is passed to `ChunkedTranscriber.start(pre_roll_audio)`
4. `AudioCapture.set_recording(True)` begins accumulating frames

### During Recording

1. Audio callback appends frames to both ring buffer and active buffer
2. `ChirpApp` periodically calls `ChunkedTranscriber.feed(frames)` with new audio
3. When accumulated audio >= `chunk_duration`:
   - Extract chunk with `chunk_overlap` from previous chunk end
   - Apply `trim_silence()` to reduce wasted inference
   - Enqueue chunk for worker thread
4. Worker thread calls `ParakeetManager.transcribe(chunk)` and stores result

### Recording Stop

1. `ChirpApp.on_hotkey_release()` toggles recording off
2. `AudioCapture.set_recording(False)` stops accumulating
3. `ChunkedTranscriber.finalize(timeout)`:
   - Enqueues remaining tail audio as final chunk
   - Waits for worker to drain queue
   - Merges all chunk transcripts
   - Returns final text
4. Text passes through `TextInjector.process()` and is pasted

## Components

### AudioCapture (refactored)

**New methods:**

| Method | Description |
|--------|-------------|
| `open()` | Open persistent InputStream at app startup |
| `close()` | Close stream at app shutdown |
| `set_recording(active: bool)` | Start/stop accumulating to active buffer |
| `drain_frames() -> np.ndarray` | Return and clear active buffer contents |
| `get_pre_roll(seconds: float) -> np.ndarray` | Retrieve recent audio from ring buffer |

**Ring buffer behavior:**

- Circular buffer storing last `ring_buffer_seconds` of audio
- Always receiving frames (even when not recording)
- Thread-safe read/write with lock

**Error handling:**

- Catch `sd.PortAudioError` in callback and stream operations
- Log warning and attempt to reopen stream
- Notify ChirpApp of device errors

### ChunkedTranscriber

**Public API:**

```python
class ChunkedTranscriber:
    def __init__(
        self,
        transcribe_fn: Callable[[np.ndarray], str],
        *,
        chunk_duration: float = 4.0,
        chunk_overlap: float = 0.5,
        merge_window_words: int = 5,
        max_queue_depth: int = 3,
        silence_threshold: float = 0.01,
        sample_rate: int = 16000,
    ) -> None: ...

    def start(self, pre_roll: Optional[np.ndarray] = None) -> None:
        """Begin a new transcription session."""

    def feed(self, frames: np.ndarray) -> None:
        """Add audio frames. Triggers chunk creation when buffer is full."""

    def finalize(self, timeout: Optional[float] = None) -> str:
        """Process remaining audio, wait for worker, merge and return text."""

    def shutdown(self) -> None:
        """Clean shutdown of worker thread."""
```

**Internal state:**

- `_buffer: np.ndarray` – Accumulated audio since last chunk
- `_chunk_transcripts: list[str]` – Ordered results from worker
- `_queue: queue.Queue` – Pending chunks for worker
- `_worker: threading.Thread` – Single worker calling transcribe_fn
- `_chunks_dropped: int` – Counter for overflow detection

### Merge Algorithm

The merge algorithm removes duplicate words at chunk boundaries caused by overlap.

**Steps:**

1. Tokenize both texts on whitespace
2. For comparison: strip punctuation, lowercase
3. Compare last N words of accumulated text with first N words of new chunk (N = `merge_window_words`)
4. Find longest suffix↔prefix match
5. Drop matched prefix from new chunk
6. Append remainder with single space

**Edge cases:**

| Case | Behavior |
|------|----------|
| Perfect overlap | Drop entire overlapping prefix |
| Partial overlap | Drop matched portion only |
| No overlap | Append with space |
| Divergent transcription ("I'll" vs "I will") | Keep earlier version, drop conflicting prefix |
| Empty chunk | Skip entirely |
| Single-word chunks | Include in merge window |

**Example:**

```
Accumulated: "Hello world, this is a"
New chunk:   "this is a test sentence"
Match:       "this is a" (3 words)
Result:      "Hello world, this is a test sentence"
```

### Silence Trimming

**Function signature:**

```python
def trim_silence(
    audio: np.ndarray,
    threshold: float = 0.01,
    min_duration: float = 0.1,
    sample_rate: int = 16000,
) -> np.ndarray:
    """
    Trim leading and trailing silence from audio.

    Args:
        audio: Input audio samples (float32, mono)
        threshold: RMS energy below which audio is considered silence
        min_duration: Minimum output duration in seconds
        sample_rate: Audio sample rate

    Returns:
        Trimmed audio, or original if result would be below min_duration
    """
```

**Algorithm:**

1. Compute RMS energy in small windows (e.g., 10ms)
2. Find first/last window exceeding threshold
3. Return slice, ensuring at least `min_duration` seconds
4. If entirely silent, return minimal audio (avoid empty chunks)

## Configuration

New fields in `ChirpConfig`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `streaming_transcription` | `bool` | `true` | Enable chunked background transcription |
| `chunk_duration` | `float` | `4.0` | Seconds per chunk |
| `chunk_overlap` | `float` | `0.5` | Overlap between chunks |
| `pre_roll_seconds` | `float` | `0.2` | Audio captured before hotkey press |
| `ring_buffer_seconds` | `float` | `10.0` | Ring buffer size |
| `merge_window_words` | `int` | `5` | Words compared for overlap detection |
| `max_chunk_queue_depth` | `int` | `3` | Max pending chunks before fallback |
| `silence_threshold` | `float` | `0.01` | RMS threshold for silence (0 disables) |

**Validation rules:**

- `chunk_duration > chunk_overlap >= 0`
- `chunk_duration >= 1.0`
- `ring_buffer_seconds >= chunk_duration + pre_roll_seconds`
- `merge_window_words >= 1`
- `max_chunk_queue_depth >= 1`
- `silence_threshold >= 0`

## Error Handling

### Queue Overflow

When `_queue.qsize() >= max_chunk_queue_depth`:

1. Log warning: "Chunk queue full, dropping chunk"
2. Increment `_chunks_dropped` counter
3. Do not enqueue new chunk
4. On finalize: if `_chunks_dropped > 0`, fall back to full-utterance transcription

### Finalization Timeout

When worker doesn't drain within `chunk_duration * 2`:

1. Log warning: "Finalization timeout, using partial results"
2. Merge available transcripts
3. Return partial text (do not fall back to full-utterance)

### Device Errors

When `sd.PortAudioError` occurs:

1. Log warning with error details
2. Attempt to close and reopen stream
3. If recovery fails, disable streaming for this session
4. Notify user via status callback

## Fallback Behavior

Fall back to full-utterance transcription when:

1. `streaming_transcription = false` (config)
2. Any chunks were dropped (queue overflow)
3. Worker thread crashes

Fallback behavior:

1. Collect all audio from `AudioCapture.drain_frames()`
2. Call `ParakeetManager.transcribe(full_audio)` directly
3. Proceed with text injection as before

## Rapid Toggle Handling

If user toggles on→off→on before finalization completes:

1. Block new recording start
2. Log debug: "Waiting for previous transcription to complete"
3. Wait for finalization to finish
4. Then start new recording

Implementation: `_finalization_in_progress` flag in ChirpApp.

## Model Timeout Interaction

When `streaming_transcription = true`:

- Set `model_timeout = 0` internally (never unload)
- Ignore config file value for `model_timeout`
- Keep model warm for instant chunk processing

Document this behavior in config.toml comments.

## Instrumentation

Debug logging includes:

| Event | Logged Data |
|-------|-------------|
| Chunk created | Duration (ms), silence trimmed (ms) |
| Chunk enqueued | Queue depth |
| Chunk transcribed | Transcription time (ms), text length |
| Merge performed | Overlap words found, words dropped |
| Finalization complete | Total time (ms), chunks processed, any fallback |
| Device error | Error type, recovery status |

## Testing Strategy

### Unit Tests (test_chunked_transcriber.py)

**Merge logic:**

- Perfect overlap (identical words)
- Partial overlap (subset match)
- No overlap (clean append)
- Punctuation at boundaries
- Divergent transcriptions
- Empty/silent chunks
- Single-word chunks

**Silence trimming:**

- Trim leading silence
- Trim trailing silence
- Preserve minimum duration
- Handle all-silent audio
- Handle no-silence audio

### Ring Buffer Tests

- Buffer wrapping (overflow)
- Pre-roll retrieval accuracy
- Concurrent read/write safety

### Integration Tests

- Full record → chunk → merge → inject cycle
- Rapid toggle handling
- Queue overflow → fallback
- Device error recovery
- Config validation

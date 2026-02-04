import pytest
from chirp.text_merge import merge_transcripts


class TestMergeTranscripts:
    """Tests for the transcript merge algorithm."""

    def test_perfect_overlap(self):
        """Single word overlap should be detected and merged."""
        result = merge_transcripts("hello world", "world says hi")
        assert result == "hello world says hi"

    def test_partial_overlap(self):
        """Partial word overlap at boundary should merge correctly."""
        result = merge_transcripts("the quick brown", "brown fox jumps")
        assert result == "the quick brown fox jumps"

    def test_no_overlap(self):
        """No overlap should simply concatenate with space."""
        result = merge_transcripts("hello", "world")
        assert result == "hello world"

    def test_punctuation_preserved(self):
        """Punctuation should be preserved in output even when matching."""
        # The accumulated text has "Hello." and new chunk has "Hello,"
        # They should match (ignoring punctuation) and preserve accumulated's version
        result = merge_transcripts("Hello.", "Hello, world")
        assert result == "Hello. world"

    def test_empty_chunk_skipped(self):
        """Empty new chunk should return accumulated unchanged."""
        assert merge_transcripts("hello", "") == "hello"
        assert merge_transcripts("hello", "   ") == "hello"

    def test_empty_accumulated(self):
        """Empty accumulated should return new chunk."""
        assert merge_transcripts("", "world") == "world"
        assert merge_transcripts("   ", "world") == "world"

    def test_case_insensitive(self):
        """Overlap detection should be case-insensitive."""
        result = merge_transcripts("Hello", "hello world")
        assert result == "Hello world"

    def test_multi_word_overlap(self):
        """Multiple words overlapping should be handled."""
        result = merge_transcripts("one two three", "two three four")
        assert result == "one two three four"

    def test_full_overlap(self):
        """Complete overlap of new chunk should not duplicate."""
        result = merge_transcripts("hello world", "world")
        assert result == "hello world"

    def test_window_limits_search(self):
        """Overlap detection should respect window parameter."""
        # With window=2, we only look at last 2 words of accumulated
        # and first 2 words of new chunk for overlap
        result = merge_transcripts("a b c d", "c d e f", window=2)
        # "c d" from tail matches "c d" from head
        assert result == "a b c d e f"

    def test_punctuation_in_middle(self):
        """Words with punctuation in middle should still match."""
        result = merge_transcripts("don't stop", "stop believing")
        assert result == "don't stop believing"

    def test_divergent_transcriptions(self):
        """Divergent transcriptions should prefer earlier accumulated text."""
        # When transcriptions diverge (contractions vs full words),
        # the accumulated version should be kept for matching words
        result = merge_transcripts("I'll go", "I will go there")
        # "I'll" normalizes to "Ill" and "I" normalizes to "I" - no overlap
        # Should concatenate since normalized forms don't match
        assert result == "I'll go I will go there"

    def test_single_word_chunks(self):
        """Single word chunks should merge correctly."""
        result = merge_transcripts("a", "a b")
        assert result == "a b"

    def test_whitespace_only_chunk(self):
        """Whitespace-only new chunk should return accumulated unchanged."""
        result = merge_transcripts("hello", "   ")
        assert result == "hello"
        # Multiple whitespace characters
        result = merge_transcripts("hello world", "\t\n  ")
        assert result == "hello world"

    def test_multiple_consecutive_merges(self):
        """Chain of 3+ merges should accumulate correctly."""
        # Simulate streaming transcription with overlapping chunks
        result = merge_transcripts("The quick", "quick brown")
        assert result == "The quick brown"
        
        result = merge_transcripts(result, "brown fox")
        assert result == "The quick brown fox"
        
        result = merge_transcripts(result, "fox jumps over")
        assert result == "The quick brown fox jumps over"
        
        result = merge_transcripts(result, "over the lazy")
        assert result == "The quick brown fox jumps over the lazy"
        
        result = merge_transcripts(result, "lazy dog")
        assert result == "The quick brown fox jumps over the lazy dog"

    def test_long_overlap_window(self):
        """Window larger than text length should handle gracefully."""
        # Window=10 on text with fewer than 10 words
        result = merge_transcripts("hi there", "there friend", window=10)
        assert result == "hi there friend"
        
        # Window much larger than both texts
        result = merge_transcripts("a b", "b c", window=100)
        assert result == "a b c"

    def test_numbers_and_special_chars(self):
        """Numbers and special characters should be handled correctly."""
        result = merge_transcripts("test 123", "123 456")
        assert result == "test 123 456"
        
        # Mixed numbers and text
        result = merge_transcripts("item 42 is", "42 is ready")
        assert result == "item 42 is ready"
        
        # Special characters (should be stripped for comparison)
        result = merge_transcripts("$100 price", "price is low")
        assert result == "$100 price is low"

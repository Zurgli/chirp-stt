import re
from typing import List


def merge_transcripts(accumulated: str, new_chunk: str, window: int = 5) -> str:
    """
    Merge two transcript chunks, removing duplicate words from overlap.
    
    Args:
        accumulated: The accumulated transcript so far
        new_chunk: The new chunk to merge
        window: Number of words to compare for overlap detection
        
    Returns:
        Merged transcript with duplicates removed
    """
    # Handle empty inputs
    if not new_chunk or new_chunk.isspace():
        return accumulated
    if not accumulated or accumulated.isspace():
        return new_chunk.strip()
    
    accumulated = accumulated.strip()
    new_chunk = new_chunk.strip()
    
    # Tokenize on whitespace (preserving original tokens with punctuation)
    acc_tokens = accumulated.split()
    new_tokens = new_chunk.split()
    
    if not acc_tokens or not new_tokens:
        return (accumulated + " " + new_chunk).strip()
    
    # Helper to strip punctuation for comparison
    def normalize(word: str) -> str:
        return re.sub(r'[^\w]', '', word).lower()
    
    # Get the last N words from accumulated and first N from new_chunk
    acc_tail = acc_tokens[-window:]
    new_head = new_tokens[:window]
    
    # Normalize for comparison
    acc_tail_normalized = [normalize(w) for w in acc_tail]
    new_head_normalized = [normalize(w) for w in new_head]
    
    # Find longest matching suffix of acc_tail with prefix of new_head
    overlap_len = 0
    for start in range(len(acc_tail)):
        suffix = acc_tail_normalized[start:]
        suffix_len = len(suffix)
        
        # Check if this suffix matches a prefix of new_head
        if suffix_len <= len(new_head_normalized):
            prefix = new_head_normalized[:suffix_len]
            if suffix == prefix:
                # Found a match - use the longest one
                if suffix_len > overlap_len:
                    overlap_len = suffix_len
    
    # Drop the overlapping prefix from new_chunk and append remainder
    remainder = new_tokens[overlap_len:]
    
    if remainder:
        return accumulated + " " + " ".join(remainder)
    else:
        return accumulated

"""Domain chunking utilities for large scans."""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChunkInfo:
    """Information about the current chunk being processed."""
    current: int  # 1-indexed chunk number
    total: int  # Total number of chunks
    domains: list[dict]  # Domains in this chunk
    all_domain_count: int  # Total domains before chunking

    @property
    def is_chunked(self) -> bool:
        """Return True if this is a chunked run (not all domains at once)."""
        return self.total > 1

    @property
    def progress_str(self) -> str:
        """Return progress string like 'Chunk 2/4'."""
        return f"Chunk {self.current}/{self.total}"

    @property
    def domain_range_str(self) -> str:
        """Return domain range string like 'domains 6-10 of 29'."""
        if not self.domains:
            return "no domains"
        start = (self.current - 1) * len(self.domains) + 1
        end = start + len(self.domains) - 1
        return f"domains {start}-{end} of {self.all_domain_count}"


def parse_chunk_spec(chunk_spec: str) -> tuple[int, int]:
    """
    Parse a chunk specification like '2/4' into (current, total).

    Args:
        chunk_spec: String in format 'N/M' where N is current chunk and M is total

    Returns:
        Tuple of (current_chunk, total_chunks), both 1-indexed

    Raises:
        ValueError: If the format is invalid
    """
    if "/" not in chunk_spec:
        raise ValueError(f"Invalid chunk format '{chunk_spec}'. Expected 'N/M' (e.g., '2/4')")

    parts = chunk_spec.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid chunk format '{chunk_spec}'. Expected 'N/M' (e.g., '2/4')")

    try:
        current = int(parts[0])
        total = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid chunk numbers in '{chunk_spec}'. Expected integers.")

    if current < 1:
        raise ValueError(f"Chunk number must be >= 1, got {current}")
    if total < 1:
        raise ValueError(f"Total chunks must be >= 1, got {total}")
    if current > total:
        raise ValueError(f"Chunk {current} exceeds total chunks {total}")

    return current, total


def split_into_chunks(domains: list[dict], chunk_size: int) -> list[list[dict]]:
    """
    Split a list of domains into chunks of the specified size.

    Args:
        domains: List of domain configurations
        chunk_size: Maximum domains per chunk

    Returns:
        List of domain lists (chunks)
    """
    if chunk_size < 1:
        raise ValueError(f"Chunk size must be >= 1, got {chunk_size}")

    if not domains:
        return []

    chunks = []
    for i in range(0, len(domains), chunk_size):
        chunks.append(domains[i:i + chunk_size])

    return chunks


def get_chunk_by_spec(domains: list[dict], current: int, total: int) -> list[dict]:
    """
    Get domains for a specific chunk number.

    Distributes domains as evenly as possible across chunks.
    Extra domains are distributed to earlier chunks.

    Args:
        domains: Full list of domains
        current: Current chunk number (1-indexed)
        total: Total number of chunks

    Returns:
        List of domains for this chunk
    """
    if not domains:
        return []

    if current < 1 or current > total:
        raise ValueError(f"Invalid chunk {current}/{total}")

    n = len(domains)
    base_size = n // total
    remainder = n % total

    # Calculate start and end indices
    # Earlier chunks get one extra domain if there's a remainder
    start = 0
    for i in range(1, current):
        start += base_size + (1 if i <= remainder else 0)

    size = base_size + (1 if current <= remainder else 0)
    end = start + size

    return domains[start:end]


def calculate_chunks(
    domains: list[dict],
    chunk_size: Optional[int] = None,
    chunk_spec: Optional[str] = None,
) -> ChunkInfo:
    """
    Calculate chunk information based on chunking options.

    Args:
        domains: Full list of domains
        chunk_size: If provided, auto-chunk into batches of this size
        chunk_spec: If provided, manual chunk specification like '2/4'

    Returns:
        ChunkInfo with the domains to process and chunk metadata

    Note:
        If both chunk_size and chunk_spec are provided, chunk_spec takes precedence.
        If neither is provided, returns all domains as a single chunk.
    """
    all_count = len(domains)

    # Manual chunk specification takes precedence
    if chunk_spec:
        current, total = parse_chunk_spec(chunk_spec)
        chunk_domains = get_chunk_by_spec(domains, current, total)
        return ChunkInfo(
            current=current,
            total=total,
            domains=chunk_domains,
            all_domain_count=all_count,
        )

    # Auto-chunking by size (returns first chunk info for display)
    if chunk_size and chunk_size < len(domains):
        total = math.ceil(len(domains) / chunk_size)
        first_chunk = domains[:chunk_size]
        return ChunkInfo(
            current=1,
            total=total,
            domains=first_chunk,
            all_domain_count=all_count,
        )

    # No chunking - return all domains
    return ChunkInfo(
        current=1,
        total=1,
        domains=domains,
        all_domain_count=all_count,
    )

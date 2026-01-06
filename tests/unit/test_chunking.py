"""Unit tests for chunking utilities."""

import pytest

from src.utils.chunking import (
    ChunkInfo,
    parse_chunk_spec,
    split_into_chunks,
    get_chunk_by_spec,
    calculate_chunks,
)


class TestParseChunkSpec:
    """Tests for parse_chunk_spec function."""

    def test_valid_spec(self):
        """Should parse valid chunk specification."""
        assert parse_chunk_spec("1/4") == (1, 4)
        assert parse_chunk_spec("2/4") == (2, 4)
        assert parse_chunk_spec("4/4") == (4, 4)
        assert parse_chunk_spec("1/1") == (1, 1)
        assert parse_chunk_spec("10/20") == (10, 20)

    def test_invalid_format_no_slash(self):
        """Should raise ValueError for missing slash."""
        with pytest.raises(ValueError) as exc_info:
            parse_chunk_spec("24")
        assert "Expected 'N/M'" in str(exc_info.value)

    def test_invalid_format_too_many_parts(self):
        """Should raise ValueError for too many slashes."""
        with pytest.raises(ValueError) as exc_info:
            parse_chunk_spec("1/2/3")
        assert "Expected 'N/M'" in str(exc_info.value)

    def test_invalid_non_integer(self):
        """Should raise ValueError for non-integer values."""
        with pytest.raises(ValueError) as exc_info:
            parse_chunk_spec("a/b")
        assert "Expected integers" in str(exc_info.value)

    def test_invalid_chunk_zero(self):
        """Should raise ValueError for chunk number 0."""
        with pytest.raises(ValueError) as exc_info:
            parse_chunk_spec("0/4")
        assert "must be >= 1" in str(exc_info.value)

    def test_invalid_total_zero(self):
        """Should raise ValueError for total chunks 0."""
        with pytest.raises(ValueError) as exc_info:
            parse_chunk_spec("1/0")
        assert "must be >= 1" in str(exc_info.value)

    def test_invalid_chunk_exceeds_total(self):
        """Should raise ValueError when chunk exceeds total."""
        with pytest.raises(ValueError) as exc_info:
            parse_chunk_spec("5/4")
        assert "exceeds total" in str(exc_info.value)


class TestSplitIntoChunks:
    """Tests for split_into_chunks function."""

    def test_even_split(self):
        """Should split evenly when domains divide evenly."""
        domains = [{"id": f"d{i}"} for i in range(10)]
        chunks = split_into_chunks(domains, 5)

        assert len(chunks) == 2
        assert len(chunks[0]) == 5
        assert len(chunks[1]) == 5

    def test_uneven_split(self):
        """Should handle uneven splits correctly."""
        domains = [{"id": f"d{i}"} for i in range(7)]
        chunks = split_into_chunks(domains, 3)

        assert len(chunks) == 3
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 3
        assert len(chunks[2]) == 1

    def test_chunk_size_larger_than_list(self):
        """Should return single chunk when chunk_size > domain count."""
        domains = [{"id": f"d{i}"} for i in range(3)]
        chunks = split_into_chunks(domains, 10)

        assert len(chunks) == 1
        assert len(chunks[0]) == 3

    def test_chunk_size_one(self):
        """Should create one chunk per domain."""
        domains = [{"id": f"d{i}"} for i in range(3)]
        chunks = split_into_chunks(domains, 1)

        assert len(chunks) == 3
        assert all(len(c) == 1 for c in chunks)

    def test_empty_list(self):
        """Should return empty list for empty input."""
        assert split_into_chunks([], 5) == []

    def test_invalid_chunk_size(self):
        """Should raise ValueError for chunk_size < 1."""
        with pytest.raises(ValueError):
            split_into_chunks([{"id": "d1"}], 0)


class TestGetChunkBySpec:
    """Tests for get_chunk_by_spec function."""

    def test_even_distribution(self):
        """Should distribute domains evenly when possible."""
        domains = [{"id": f"d{i}"} for i in range(8)]

        chunk1 = get_chunk_by_spec(domains, 1, 4)
        chunk2 = get_chunk_by_spec(domains, 2, 4)
        chunk3 = get_chunk_by_spec(domains, 3, 4)
        chunk4 = get_chunk_by_spec(domains, 4, 4)

        assert len(chunk1) == 2
        assert len(chunk2) == 2
        assert len(chunk3) == 2
        assert len(chunk4) == 2

        # Verify all domains are covered exactly once
        all_ids = [d["id"] for c in [chunk1, chunk2, chunk3, chunk4] for d in c]
        assert sorted(all_ids) == sorted(d["id"] for d in domains)

    def test_uneven_distribution(self):
        """Should distribute remainder to earlier chunks."""
        domains = [{"id": f"d{i}"} for i in range(10)]

        chunk1 = get_chunk_by_spec(domains, 1, 3)
        chunk2 = get_chunk_by_spec(domains, 2, 3)
        chunk3 = get_chunk_by_spec(domains, 3, 3)

        # 10 / 3 = 3 remainder 1
        # Chunks 1 gets extra: 4, 3, 3
        assert len(chunk1) == 4
        assert len(chunk2) == 3
        assert len(chunk3) == 3

        # Verify coverage
        all_ids = [d["id"] for c in [chunk1, chunk2, chunk3] for d in c]
        assert sorted(all_ids) == sorted(d["id"] for d in domains)

    def test_single_chunk(self):
        """Should return all domains for 1/1."""
        domains = [{"id": f"d{i}"} for i in range(5)]
        chunk = get_chunk_by_spec(domains, 1, 1)

        assert len(chunk) == 5
        assert chunk == domains

    def test_more_chunks_than_domains(self):
        """Should handle case where chunks > domains."""
        domains = [{"id": f"d{i}"} for i in range(3)]

        chunk1 = get_chunk_by_spec(domains, 1, 5)
        chunk2 = get_chunk_by_spec(domains, 2, 5)
        chunk3 = get_chunk_by_spec(domains, 3, 5)
        chunk4 = get_chunk_by_spec(domains, 4, 5)
        chunk5 = get_chunk_by_spec(domains, 5, 5)

        # 3 domains across 5 chunks = 1,1,1,0,0
        assert len(chunk1) == 1
        assert len(chunk2) == 1
        assert len(chunk3) == 1
        assert len(chunk4) == 0
        assert len(chunk5) == 0

    def test_empty_domains(self):
        """Should return empty list for empty input."""
        assert get_chunk_by_spec([], 1, 4) == []

    def test_preserves_order(self):
        """Should preserve domain order within chunks."""
        domains = [{"id": f"d{i}"} for i in range(6)]
        chunk1 = get_chunk_by_spec(domains, 1, 2)
        chunk2 = get_chunk_by_spec(domains, 2, 2)

        assert [d["id"] for d in chunk1] == ["d0", "d1", "d2"]
        assert [d["id"] for d in chunk2] == ["d3", "d4", "d5"]


class TestCalculateChunks:
    """Tests for calculate_chunks function."""

    def test_no_chunking(self):
        """Should return all domains when no chunking specified."""
        domains = [{"id": f"d{i}"} for i in range(5)]
        info = calculate_chunks(domains)

        assert info.current == 1
        assert info.total == 1
        assert len(info.domains) == 5
        assert info.all_domain_count == 5
        assert not info.is_chunked

    def test_manual_chunk_spec(self):
        """Should use manual chunk specification."""
        domains = [{"id": f"d{i}"} for i in range(8)]
        info = calculate_chunks(domains, chunk_spec="2/4")

        assert info.current == 2
        assert info.total == 4
        assert len(info.domains) == 2
        assert info.all_domain_count == 8
        assert info.is_chunked

    def test_auto_chunk_size(self):
        """Should calculate chunks based on chunk_size."""
        domains = [{"id": f"d{i}"} for i in range(10)]
        info = calculate_chunks(domains, chunk_size=3)

        assert info.current == 1
        assert info.total == 4  # ceil(10/3) = 4
        assert len(info.domains) == 3
        assert info.all_domain_count == 10
        assert info.is_chunked

    def test_chunk_size_larger_than_domains(self):
        """Should not chunk when chunk_size >= domain count."""
        domains = [{"id": f"d{i}"} for i in range(5)]
        info = calculate_chunks(domains, chunk_size=10)

        assert info.current == 1
        assert info.total == 1
        assert len(info.domains) == 5
        assert not info.is_chunked

    def test_chunk_spec_takes_precedence(self):
        """Manual chunk_spec should override chunk_size."""
        domains = [{"id": f"d{i}"} for i in range(10)]
        info = calculate_chunks(domains, chunk_size=3, chunk_spec="1/2")

        # chunk_spec wins
        assert info.current == 1
        assert info.total == 2
        assert len(info.domains) == 5  # Half of 10


class TestChunkInfo:
    """Tests for ChunkInfo dataclass."""

    def test_is_chunked_true(self):
        """Should return True when total > 1."""
        info = ChunkInfo(current=1, total=4, domains=[], all_domain_count=10)
        assert info.is_chunked is True

    def test_is_chunked_false(self):
        """Should return False when total == 1."""
        info = ChunkInfo(current=1, total=1, domains=[], all_domain_count=10)
        assert info.is_chunked is False

    def test_progress_str(self):
        """Should format progress string correctly."""
        info = ChunkInfo(current=2, total=4, domains=[], all_domain_count=10)
        assert info.progress_str == "Chunk 2/4"

    def test_domain_range_str(self):
        """Should format domain range string correctly."""
        domains = [{"id": f"d{i}"} for i in range(3)]
        info = ChunkInfo(current=2, total=4, domains=domains, all_domain_count=12)
        # Chunk 2 with 3 domains = domains 4-6 of 12
        assert info.domain_range_str == "domains 4-6 of 12"

    def test_domain_range_str_empty(self):
        """Should handle empty domains."""
        info = ChunkInfo(current=5, total=5, domains=[], all_domain_count=10)
        assert info.domain_range_str == "no domains"


class TestIntegration:
    """Integration tests for chunking workflow."""

    def test_full_chunking_workflow(self):
        """Test a complete chunking workflow."""
        # Simulate 29 domains (like our 'all' group)
        domains = [{"id": f"domain_{i}", "name": f"Domain {i}"} for i in range(29)]

        # Auto-chunk into batches of 5
        batches = split_into_chunks(domains, 5)

        assert len(batches) == 6  # 5+5+5+5+5+4
        assert sum(len(b) for b in batches) == 29

        # Each batch should maintain order
        all_ids = [d["id"] for batch in batches for d in batch]
        assert all_ids == [f"domain_{i}" for i in range(29)]

    def test_manual_chunk_retry_scenario(self):
        """Test using manual chunk for retry scenario."""
        domains = [{"id": f"d{i}"} for i in range(20)]

        # Suppose batch 3/4 failed and needs retry
        retry_chunk = get_chunk_by_spec(domains, 3, 4)

        assert len(retry_chunk) == 5
        assert [d["id"] for d in retry_chunk] == ["d10", "d11", "d12", "d13", "d14"]

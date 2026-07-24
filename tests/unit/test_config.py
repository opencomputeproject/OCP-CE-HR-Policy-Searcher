

def test_new_zealand_is_a_valid_region():
    """The NZ PCO source's region must validate (registry has had the row
    since the wave-1 sources PR; VALID_REGIONS lagged behind it)."""
    from src.core.config import VALID_REGIONS
    assert "new_zealand" in VALID_REGIONS

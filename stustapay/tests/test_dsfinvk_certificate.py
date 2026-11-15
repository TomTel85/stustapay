import pytest

from stustapay.dsfinvk.generator import _split_tse_certificate


@pytest.fixture(autouse=True)
async def setup_test_db_pool():
    yield None


def test_split_tse_certificate_uses_contiguous_chunks_up_to_5000_characters():
    certificate = "x" * 1001

    assert _split_tse_certificate(certificate) == ["x" * 1000, "x"]
    assert len(_split_tse_certificate("x" * 5000)) == 5


def test_split_tse_certificate_rejects_more_than_5000_characters():
    with pytest.raises(ValueError, match="maximum 5000"):
        _split_tse_certificate("x" * 5001)

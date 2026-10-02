from pathlib import Path

import pytest
from defusedxml.common import EntitiesForbidden

from stustapay.dsfinvk.dsfinvk.validate import validate_files


def test_dsfinvk_accepts_xml_without_entities(tmp_path: Path) -> None:
    index = tmp_path / "index.xml"
    index.write_text("<DataSet><Version>1.0</Version></DataSet>")
    assert validate_files({"index.xml": str(index)}) == []


def test_dsfinvk_rejects_entity_expansion(tmp_path: Path) -> None:
    index = tmp_path / "index.xml"
    index.write_text(
        '<!DOCTYPE DataSet [<!ENTITY payload "untrusted">]><DataSet><Version>&payload;</Version></DataSet>'
    )
    with pytest.raises(EntitiesForbidden):
        validate_files({"index.xml": str(index)})

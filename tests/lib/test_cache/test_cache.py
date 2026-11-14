from __future__ import annotations

import json

import msgspec
import pytest

from nrlx.io.cache import (
    decode_catalog,
    decode_prefixes,
    get_cache_root,
    get_catalog_file,
    get_prefixes_file,
    read_catalog,
    read_prefixes,
    write_catalog,
    write_prefixes,
)


def test_cache_root_custom(tmp_path):
    assert get_cache_root(tmp_path) == tmp_path.resolve()


def test_cache_root_default_is_the_user_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "nrlx.io.cache.user_cache_dir",
        lambda appname, appauthor: str(tmp_path / appname),
    )

    assert get_cache_root() == tmp_path / "nrlx"


def test_catalog_file_layout(tmp_path):
    assert get_catalog_file(tmp_path) == tmp_path.resolve() / "nrl" / "catalog.json"


def test_read_catalog(cache_root):
    catalog = read_catalog(get_catalog_file(cache_root))

    assert len(catalog.get_configurations()) == 5


def test_read_catalog_missing_file_says_sync(tmp_path):
    with pytest.raises(FileNotFoundError, match="Run 'nrlx sync'"):
        read_catalog(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "content",
    [
        # not JSON
        b"{not valid json",
        # no NRLCatalog root
        json.dumps({"nope": {}}).encode(),
        # format version as text, not a number
        json.dumps({"NRLCatalog": {"formatversion": "1.0", "element": []}}).encode(),
    ],
)
def test_read_catalog_invalid_file(tmp_path, content):
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_bytes(content)

    with pytest.raises(ValueError, match="Invalid catalog file"):
        read_catalog(catalog_file)


def test_decode_catalog_accepts_unknown_fields(catalog_content):
    data = json.loads(catalog_content)
    data["NRLCatalog"]["newfield"] = "added by the service"

    catalog = decode_catalog(json.dumps(data).encode())

    assert len(catalog.get_configurations()) == 5


def test_decode_catalog_rejects_missing_instconfig():
    content = json.dumps(
        {
            "NRLCatalog": {
                "formatversion": 1.0,
                "element": [
                    {
                        "name": "sensor",
                        "manufacturer": [
                            {
                                "name": "Streckeisen",
                                "model": [
                                    {
                                        "name": "STS-2",
                                        "configuration": [{"version": "1"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }
    ).encode()

    with pytest.raises(msgspec.ValidationError, match="instconfig"):
        decode_catalog(content)


def test_write_catalog_creates_the_folders(tmp_path):
    catalog_file = get_catalog_file(tmp_path)

    written = write_catalog(b"{}", catalog_file)

    assert written == catalog_file
    assert catalog_file.read_bytes() == b"{}"


def test_prefixes_file_layout(tmp_path):
    assert get_prefixes_file(tmp_path) == tmp_path.resolve() / "nrl" / "prefixes.json"


def test_read_prefixes(cache_root):
    prefixes = read_prefixes(get_prefixes_file(cache_root))

    assert [prefix.prefix for prefix in prefixes] == ["FR", "FV", "LP", "SG"]
    assert prefixes[0].description == "Final_Sample_Rate"
    assert prefixes[0].question == "What is the final sample rate?"


def test_read_prefixes_missing_file_says_sync(tmp_path):
    with pytest.raises(FileNotFoundError, match="Run 'nrlx sync'"):
        read_prefixes(get_prefixes_file(tmp_path))


@pytest.mark.parametrize("content", [b"", b"<html>maintenance</html>", b'{"a": 1}'])
def test_read_prefixes_invalid_file(tmp_path, content):
    prefixes_file = get_prefixes_file(tmp_path)
    write_prefixes(content, prefixes_file)

    with pytest.raises(ValueError, match="Invalid code table"):
        read_prefixes(prefixes_file)


def test_decode_prefixes_rejects_missing_description():
    content = json.dumps([{"prefix": "FR"}]).encode()

    with pytest.raises(msgspec.ValidationError, match="description"):
        decode_prefixes(content)


def test_write_prefixes_creates_the_folders(tmp_path):
    prefixes_file = get_prefixes_file(tmp_path)

    written = write_prefixes(b"[]", prefixes_file)

    assert written == prefixes_file
    assert prefixes_file.read_bytes() == b"[]"

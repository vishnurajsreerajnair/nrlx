from __future__ import annotations

from nrlx.cache import get_cache_info, init_cache, read_cache_index


def test_get_cache_info_uses_custom_root(tmp_path):
    cache = get_cache_info(tmp_path)

    assert cache.root == tmp_path.resolve()
    assert cache.nrl_dir == tmp_path.resolve() / "nrl"
    assert cache.index_file == tmp_path.resolve() / "index.json"
    assert cache.exists is True


def test_init_cache_creates_expected_files(tmp_path):
    cache = init_cache(tmp_path)

    assert cache.root.exists()
    assert cache.nrl_dir.exists()
    assert cache.index_file.exists()


def test_read_cache_index(tmp_path):
    init_cache(tmp_path)
    index = read_cache_index(tmp_path)

    assert index["schema_version"] == 1
    assert index["nrl_version"] is None
    assert index["entries"] == {}
from __future__ import annotations

from nrlx.cache import get_cache_info, init_cache


def test_get_cache_info_uses_custom_root(tmp_path):
    cache = get_cache_info(tmp_path)

    assert cache.root == tmp_path.resolve()
    assert cache.nrl_dir == tmp_path.resolve() / "nrl"
    assert cache.exists is True


def test_init_cache_creates_expected_files(tmp_path):
    cache = init_cache(tmp_path)

    assert cache.root.exists()
    assert cache.nrl_dir.exists()

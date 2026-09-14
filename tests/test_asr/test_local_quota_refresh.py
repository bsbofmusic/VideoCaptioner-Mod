"""Regression tests for the Mod's app-local fresh-quota policy."""

import pytest
from diskcache import Cache

from videocaptioner.core.asr.base import BaseASR


class DummyASR(BaseASR):
    pass


class OtherASR(BaseASR):
    pass


def _make_asr(cls: type[BaseASR], cache: Cache) -> BaseASR:
    asr = cls.__new__(cls)
    asr._cache = cache
    return asr


def _seed_usage(cache: Cache, service_name: str, count: int, duration: float) -> None:
    tag = f"rate_limit:{service_name}"
    for index in range(count):
        cache.set(
            f"rate_limit_record:{service_name}:{index}",
            duration,
            tag=tag,
            expire=24 * 3600,
        )


def _tag_keys(cache: Cache, tag: str) -> list[str]:
    query = "SELECT key FROM Cache WHERE tag = ?"
    return [row[0] for row in cache._sql(query, (tag,)).fetchall()]


@pytest.fixture
def cache(tmp_path) -> Cache:
    instance = Cache(str(tmp_path / "asr-cache"), tag_index=True)
    yield instance
    instance.close()


@pytest.mark.parametrize("count", [0, 99, 100, 101])
def test_call_count_history_is_always_normalized_to_never_used(cache: Cache, count: int) -> None:
    _seed_usage(cache, "DummyASR", count, 60.0)
    asr = _make_asr(DummyASR, cache)

    asr._check_rate_limit()

    assert _tag_keys(cache, "rate_limit:DummyASR") == []


@pytest.mark.parametrize("minutes", [359, 360, 361, 720])
def test_duration_history_is_always_normalized_to_full_quota(cache: Cache, minutes: int) -> None:
    _seed_usage(cache, "DummyASR", 1, minutes * 60.0)
    asr = _make_asr(DummyASR, cache)

    asr._check_rate_limit()

    assert _tag_keys(cache, "rate_limit:DummyASR") == []


def test_quota_refresh_is_service_scoped(cache: Cache) -> None:
    _seed_usage(cache, "DummyASR", 3, 120.0)
    _seed_usage(cache, "OtherASR", 4, 180.0)

    _make_asr(DummyASR, cache)._check_rate_limit()

    assert _tag_keys(cache, "rate_limit:DummyASR") == []
    assert len(_tag_keys(cache, "rate_limit:OtherASR")) == 4

    _make_asr(OtherASR, cache)._check_rate_limit()
    assert _tag_keys(cache, "rate_limit:OtherASR") == []


def test_quota_refresh_does_not_touch_asr_results_or_other_tags(cache: Cache) -> None:
    _seed_usage(cache, "DummyASR", 100, 3600.0)
    cache.set("DummyASR:result:abc", {"utterances": ["keep-me"]}, expire=3600)
    cache.set("other-tagged-state", "keep-me-too", tag="not-a-rate-limit", expire=3600)

    _make_asr(DummyASR, cache)._check_rate_limit()

    assert _tag_keys(cache, "rate_limit:DummyASR") == []
    assert cache.get("DummyASR:result:abc") == {"utterances": ["keep-me"]}
    assert cache.get("other-tagged-state") == "keep-me-too"
    assert _tag_keys(cache, "not-a-rate-limit") == ["other-tagged-state"]

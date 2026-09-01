"""The offline fixture and the idempotency cache."""

from datetime import date

import pytest

import fred_client


def test_frequency_changes_the_point_count():
    monthly = fred_client.get_observations("CPIAUCSL", date(2020, 1, 1), date(2020, 12, 1), "m")
    quarterly = fred_client.get_observations("CPIAUCSL", date(2020, 1, 1), date(2020, 12, 1), "q")
    daily = fred_client.get_observations("DGS10", date(2020, 1, 1), date(2020, 12, 31), "d")

    assert len(monthly) == 12
    assert len(quarterly) == 4
    assert 200 < len(daily) < 280  # ~business days in a year


def test_values_are_deterministic():
    a = fred_client.get_observations("UNRATE", date(2021, 1, 1), date(2021, 6, 1), "m")
    fred_client._cache.clear()
    b = fred_client.get_observations("UNRATE", date(2021, 1, 1), date(2021, 6, 1), "m")
    assert a == b


def test_second_identical_call_is_served_from_cache(monkeypatch):
    fred_client._cache.clear()
    calls = {"n": 0}
    real = fred_client.get_observations

    def counting(*args):
        key = fred_client._cache_key("obs", args[0], str(args[1]), str(args[2]), args[3])
        if key not in fred_client._cache:
            calls["n"] += 1
        return real(*args)

    monkeypatch.setattr(fred_client, "get_observations", counting)
    args = ("UNRATE", date(2020, 1, 1), date(2021, 1, 1), "m")
    fred_client.get_observations(*args)
    fred_client.get_observations(*args)
    fred_client.get_observations(*args)
    assert calls["n"] == 1


def test_different_args_are_a_different_cache_entry():
    fred_client._cache.clear()
    fred_client.get_observations("UNRATE", date(2020, 1, 1), date(2021, 1, 1), "m")
    fred_client.get_observations("UNRATE", date(2020, 1, 1), date(2022, 1, 1), "m")
    obs_keys = [k for k in fred_client._cache if k.startswith("obs|")]
    assert len(obs_keys) == 2


def test_unknown_series_offline_raises():
    with pytest.raises(fred_client.FredAPIError):
        fred_client.get_observations("NOTAREALSERIES", date(2020, 1, 1), date(2021, 1, 1), "m")

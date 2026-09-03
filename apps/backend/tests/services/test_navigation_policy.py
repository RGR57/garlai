import pytest

from src.services.navigation_policy import (
    LocalFixtureNavigationPolicy,
    ProductionNavigationPolicy,
)


@pytest.mark.parametrize(
    "url",
    (
        "file:///C:/private.txt",
        "javascript:alert(1)",
        "data:text/html,unsafe",
        "https://user:password@market.example/pricing",
        "http://127.0.0.1:8123/pricing",
        "https://10.0.0.1/pricing",
        "https://169.254.169.254/latest/meta-data",
    ),
)
def test_production_navigation_policy_rejects_unsafe_or_non_public_destinations(url):
    with pytest.raises(ValueError):
        ProductionNavigationPolicy().validate(url)


def test_production_navigation_policy_normalizes_allowed_public_https_url():
    assert ProductionNavigationPolicy().validate("HTTPS://Market.Example/pricing") == (
        "https://market.example/pricing"
    )


def test_local_fixture_policy_allows_only_its_exact_origin():
    policy = LocalFixtureNavigationPolicy("http://127.0.0.1:8123")

    assert policy.validate("http://127.0.0.1:8123/pricing") == (
        "http://127.0.0.1:8123/pricing"
    )
    with pytest.raises(ValueError):
        policy.validate("http://127.0.0.1:8124/pricing")
    with pytest.raises(ValueError):
        policy.validate("http://localhost:8123/pricing")

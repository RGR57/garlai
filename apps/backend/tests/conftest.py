import pytest

from tests.browser_fixture_site import LocalMarketplace


@pytest.fixture
def local_marketplace():
    marketplace = LocalMarketplace()
    marketplace.start()
    try:
        yield marketplace
    finally:
        marketplace.stop()

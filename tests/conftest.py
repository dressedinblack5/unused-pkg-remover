import pytest

from unused_pkg_remover.scanner import clear_package_caches


@pytest.fixture(autouse=True)
def _clear_package_caches():
    clear_package_caches()

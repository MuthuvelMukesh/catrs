from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
AUDIT_DIR = str(ROOT_DIR / "services" / "audit-service")


def _purge_app_modules():
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]


def _set_active_service(service_path: str):
    _purge_app_modules()
    # Remove other service from sys.path if present
    other = AUDIT_DIR if service_path == ROUTING_DIR else ROUTING_DIR
    while other in sys.path:
        sys.path.remove(other)
    while service_path in sys.path:
        sys.path.remove(service_path)
    sys.path.insert(0, service_path)


def pytest_collect_file(file_path: Path, parent):
    p_str = str(file_path)
    if "services" + os.sep + "routing-engine" in p_str:
        _set_active_service(ROUTING_DIR)
    elif "services" + os.sep + "audit-service" in p_str:
        _set_active_service(AUDIT_DIR)
    return None


@pytest.fixture(autouse=True)
def _service_path_setup(request):
    fpath = str(request.fspath)
    if "services" + os.sep + "routing-engine" in fpath or "tests" + os.sep + "benchmarks" in fpath:
        _set_active_service(ROUTING_DIR)
    elif "services" + os.sep + "audit-service" in fpath:
        _set_active_service(AUDIT_DIR)
    yield

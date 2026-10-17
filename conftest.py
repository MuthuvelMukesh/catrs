from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
AUDIT_DIR = str(ROOT_DIR / "services" / "audit-service")

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if ROUTING_DIR not in sys.path:
    sys.path.insert(0, ROUTING_DIR)


def _purge_app_modules():
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]


def _set_active_service(service_path: str):
    _purge_app_modules()
    other = AUDIT_DIR if service_path == ROUTING_DIR else ROUTING_DIR
    while other in sys.path:
        sys.path.remove(other)
    while service_path in sys.path:
        sys.path.remove(service_path)
    sys.path.insert(0, service_path)
    if str(ROOT_DIR) not in sys.path:
        sys.path.append(str(ROOT_DIR))


def pytest_collect_file(file_path: Path, parent):
    p_str = str(file_path).replace("\\", "/")
    if "services/routing-engine" in p_str or ("tests" in p_str and "services/audit-service" not in p_str):
        _set_active_service(ROUTING_DIR)
    elif "services/audit-service" in p_str:
        _set_active_service(AUDIT_DIR)
    return None


def pytest_pycollect_makemodule(module_path, parent):
    p_str = str(module_path).replace("\\", "/")
    if "services/routing-engine" in p_str or ("tests" in p_str and "services/audit-service" not in p_str):
        _set_active_service(ROUTING_DIR)
    elif "services/audit-service" in p_str:
        _set_active_service(AUDIT_DIR)
    return None


@pytest.fixture(autouse=True)
def _service_path_setup(request):
    fpath = str(request.fspath).replace("\\", "/")
    if "services/routing-engine" in fpath or ("tests" in fpath and "services/audit-service" not in fpath):
        _set_active_service(ROUTING_DIR)
    elif "services/audit-service" in fpath:
        _set_active_service(AUDIT_DIR)
    yield

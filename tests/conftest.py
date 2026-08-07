import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "Qwen_python_20251111_qg1ocrn27-SMC-XAUUSD.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("smc_xauusd", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def smc():
    return _load_module()


@pytest.fixture(scope="session")
def client(smc):
    from fastapi.testclient import TestClient

    return TestClient(smc.app)

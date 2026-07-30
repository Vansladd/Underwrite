import importlib.util
import sys
from pathlib import Path

import pytest

# Mounted read-only by docker-compose; the zips live outside the api package by design (D-031).
HANDLERS = Path("/lambdas")
PARAM = "/underwrite/sweeper-token"

pytestmark = pytest.mark.skipif(not HANDLERS.is_dir(), reason="lambdas/ is not mounted")


def load(name):
    """A fresh module object per test, which is also how the _TOKEN cache gets reset."""
    path = HANDLERS / name / "handler.py"
    spec = importlib.util.spec_from_file_location(f"_probe_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSsm:
    def __init__(self, value="from-ssm"):
        self.value = value
        self.calls = []

    def get_parameter(self, **kwargs):
        self.calls.append(kwargs)
        return {"Parameter": {"Value": self.value}}


@pytest.fixture
def fake_boto3(monkeypatch):
    ssm = FakeSsm()
    module = type(sys)("boto3")
    module.client = lambda service: ssm
    monkeypatch.setitem(sys.modules, "boto3", module)
    return ssm


# Both files carry their own copy: they are separately packaged zips, so this is the only thing
# that notices when one drifts from the other.
@pytest.mark.parametrize("name", ["quote_expiry", "bordereau"])
class TestSweeperToken:
    def test_the_environment_wins_and_aws_is_never_called(self, name, monkeypatch, fake_boto3):
        monkeypatch.setenv("SWEEPER_TOKEN", "from-env")
        monkeypatch.setenv("SWEEPER_TOKEN_PARAM", PARAM)

        assert load(name)._token() == "from-env"
        assert fake_boto3.calls == []

    def test_an_empty_environment_token_does_not_count_as_set(self, name, monkeypatch, fake_boto3):
        # "" would otherwise be sent as the header and 401, which reads like a wrong secret.
        monkeypatch.setenv("SWEEPER_TOKEN", "")
        monkeypatch.setenv("SWEEPER_TOKEN_PARAM", PARAM)

        assert load(name)._token() == "from-ssm"

    def test_it_decrypts_the_named_parameter(self, name, monkeypatch, fake_boto3):
        monkeypatch.delenv("SWEEPER_TOKEN", raising=False)
        monkeypatch.setenv("SWEEPER_TOKEN_PARAM", PARAM)

        assert load(name)._token() == "from-ssm"
        assert fake_boto3.calls == [{"Name": PARAM, "WithDecryption": True}]

    def test_the_lookup_is_cached_across_invocations(self, name, monkeypatch, fake_boto3):
        monkeypatch.delenv("SWEEPER_TOKEN", raising=False)
        monkeypatch.setenv("SWEEPER_TOKEN_PARAM", PARAM)
        module = load(name)

        assert [module._token(), module._token(), module._token()] == ["from-ssm"] * 3
        assert len(fake_boto3.calls) == 1

    def test_the_zip_imports_nothing_it_does_not_package(self, name):
        # boto3 comes from the managed runtime; a top-level import would still be a packaging lie,
        # because `python3 handler.py` has to keep working with only stdlib present.
        source = (HANDLERS / name / "handler.py").read_text()
        top_level = [line for line in source.splitlines() if line.startswith(("import ", "from "))]

        assert top_level == ["import json", "import os", "import urllib.request"]

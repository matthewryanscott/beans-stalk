from beans.models import Bean, BeanId, Dep
from beans_stalk.graph.layout import build_dag
from beans_stalk.graph.layouts import PROVIDERS, get_provider


def _bean(id_: str, title: str) -> Bean:
    return Bean(id=BeanId(id_), title=title, status="open")


def _dep(from_id: str, to_id: str) -> Dep:
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestRegistry:
    def test_sugiyama_registered(self):
        assert "sugiyama" in PROVIDERS

    def test_get_provider_returns_module(self):
        provider = get_provider("sugiyama")
        assert provider.KEY == "sugiyama"
        assert provider.NAME == "Sugiyama"
        assert callable(provider.compute)

    def test_get_provider_fallback(self):
        provider = get_provider("nonexistent")
        assert provider.KEY == "sugiyama"


class TestSugiyamaProvider:
    def test_compute_returns_positions(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        provider = get_provider("sugiyama")
        positions = provider.compute(g, {"bean-00000001", "bean-00000002"})
        assert "bean-00000001" in positions
        assert "bean-00000002" in positions

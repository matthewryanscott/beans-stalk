from beans_stalk.graph.layouts import _sugiyama

PROVIDERS: dict[str, object] = {}
DEFAULT_KEY = "sugiyama"


def _register(module):
    PROVIDERS[module.KEY] = module


_register(_sugiyama)


def get_provider(key: str):
    return PROVIDERS.get(key, PROVIDERS[DEFAULT_KEY])

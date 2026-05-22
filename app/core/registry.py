from app.core.models import ScenarioDescriptor
from app.core.scenario import Scenario


class ScenarioRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Scenario] = {}

    def register(self, scenario: Scenario) -> None:
        self._items[scenario.name] = scenario

    def list_descriptors(self) -> list[ScenarioDescriptor]:
        return [scenario.descriptor() for scenario in self._items.values()]

    def get(self, name: str) -> Scenario:
        return self._items[name]


registry = ScenarioRegistry()


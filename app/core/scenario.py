from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.core.models import ConversationRecord, ScenarioDescriptor


RequestT = TypeVar("RequestT", bound=BaseModel)


class Scenario(Generic[RequestT], ABC):
    name: str
    title: str
    description: str
    status: str
    endpoint: str
    agent_roles: list[str]

    def descriptor(self) -> ScenarioDescriptor:
        return ScenarioDescriptor(
            name=self.name,
            title=self.title,
            description=self.description,
            status=self.status,
            agent_roles=self.agent_roles,
            endpoint=self.endpoint,
        )

    @abstractmethod
    def simulate(self, request: RequestT) -> ConversationRecord:
        """Generate one conversation record from a scenario request."""


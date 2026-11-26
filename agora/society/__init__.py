"""Native society layer: agent-to-agent conversations that need no simulated platform."""
from .store import (
    CONVERSATION_KINDS, SocietyError, SocietyStore,
)

__all__ = ["CONVERSATION_KINDS", "SocietyError", "SocietyStore"]

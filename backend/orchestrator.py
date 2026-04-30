"""Top-level coordinator that wires Planner, ResearchLoop, and ToolDispatcher."""

import logging
import uuid
from .groq_client import get_groq_client
from .tools import ToolRegistry
from .planner import Planner
from .tool_dispatcher import ToolDispatcher
from .research_loop import ResearchLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class Orchestrator:
    """Wires together Planner → ResearchLoop → ToolDispatcher for a single run.

    Owns no business logic — its only job is construction and delegation.
    """

    def __init__(self) -> None:
        client = get_groq_client()
        tools = ToolRegistry()
        self._planner = Planner(client)
        self._dispatcher = ToolDispatcher(tools)
        self._loop = ResearchLoop(client, self._dispatcher)

    def run(self, topic: str) -> str:
        """Run a full research session and return the final answer.

        Args:
            topic: The user's raw research question or topic.

        Returns:
            The synthesised final answer string.
        """
        trace_id = uuid.uuid4().hex[:8]
        logger.info("[%s] START topic=%r", trace_id, topic)

        sub_questions = self._planner.decompose(topic, trace_id)
        if len(sub_questions) == 1 and sub_questions[0] == topic:
            scoped_topic = topic
        else:
            scoped_topic = (
                "Research these specific sub-questions and answer each one:\n"
                + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
            )

        return self._loop.run(scoped_topic, trace_id)

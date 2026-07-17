import unittest
from collections.abc import Sequence

from backend.interfaces import ContextBuilder, RetrievalResult


class CompactContextBuilder:
    """Test double demonstrating the ContextBuilder contract."""

    def build(
        self, query: str, results: Sequence[RetrievalResult], *, max_chars: int
    ) -> str:
        lines = [f"[{item.source_kind}:{item.source_id}] {item.content}" for item in results]
        return "\n".join(lines)[:max_chars]


class InterfaceContractTests(unittest.TestCase):
    def test_context_implementation_honors_budget_and_provenance(self) -> None:
        builder: ContextBuilder = CompactContextBuilder()
        result = RetrievalResult("Drone uses Raspberry Pi", 0.92, "chunk", "ch1", "c1")
        context = builder.build("reduce latency", [result], max_chars=24)
        self.assertLessEqual(len(context), 24)
        self.assertTrue(context.startswith("[chunk:ch1]"))


if __name__ == "__main__":
    unittest.main()


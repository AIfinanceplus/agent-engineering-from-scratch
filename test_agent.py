import unittest

from agent import calculator, run_agent


class AgentV0Tests(unittest.TestCase):
    def test_calculator_add(self):
        self.assertEqual(calculator(10, 20, "add"), 30)

    def test_calculator_multiply(self):
        self.assertEqual(calculator(6, 7, "multiply"), 42)

    def test_agent_completes_tool_loop(self):
        self.assertEqual(
            run_agent("Please calculate 10 + 20."),
            "The result is 30.",
        )


if __name__ == "__main__":
    unittest.main()

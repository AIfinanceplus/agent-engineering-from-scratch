from agent import run_agent
from model_adapters import OpenAIModel


if __name__ == "__main__":
    question = input("Ask: ").strip()
    answer = run_agent(
        question,
        model=OpenAIModel(),
    )
    print(answer)

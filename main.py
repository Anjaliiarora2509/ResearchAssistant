from orchestrator import Orchestrator


def main():
    try:
        orchestrator = Orchestrator()

        topic = input("Enter a question or topic to search: ").strip()
        if not topic:
            raise ValueError("No topic entered. Please provide a question or topic.")

        result = orchestrator.run(topic)

        print("Response from Groq:")
        print(result)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()

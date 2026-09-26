import argparse

from app.config import Settings, get_settings
from app.services.ollama import OllamaAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify schema-constrained Ollama analysis.")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    configured = get_settings()
    settings = Settings(**{
        **configured.model_dump(),
        "ollama_model": args.model or configured.ollama_model,
    })
    analyzer = OllamaAnalyzer(settings)
    print(analyzer.status())
    result = analyzer.analyze(
        "An update about your application",
        "recruiting@example.test",
        "We enjoyed meeting you and would like to move you to the next stage. Details will follow.",
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

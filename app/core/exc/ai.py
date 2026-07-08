# AI exceptions: the gateway/model is down vs. the model answered garbage.


class AIProviderError(Exception):
    """The AI service (or Ollama behind it) is unreachable / errored."""

    def __init__(self, message: str = "AI service is unavailable") -> None:
        self.message = message
        super().__init__(message)


class AIResponseValidationError(Exception):
    """The model's output could not be parsed into the expected schema."""

    def __init__(self, message: str = "AI returned invalid output") -> None:
        self.message = message
        super().__init__(message)

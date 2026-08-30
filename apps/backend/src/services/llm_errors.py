class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        provider: str,
        model: str | None,
        retryable: bool,
    ):
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.model = model
        self.retryable = retryable


class LLMConfigurationError(LLMError):
    pass


class LLMProviderUnavailableError(LLMError):
    pass


class LLMModelUnavailableError(LLMError):
    pass


class LLMCredentialsError(LLMError):
    pass


class LLMMalformedResponseError(LLMError):
    pass

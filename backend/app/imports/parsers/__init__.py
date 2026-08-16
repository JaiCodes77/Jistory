from app.imports.parsers.base import (
    ConversationParser,
    ParsedConversation,
    ParsedMessage,
    ParseResult,
    UnknownSourceError,
)

PARSER_REGISTRY: dict[str, type[ConversationParser]] | None = None


def _registry() -> dict[str, type[ConversationParser]]:
    global PARSER_REGISTRY
    if PARSER_REGISTRY is None:
        from app.imports.parsers.chatgpt import ChatGPTParser

        PARSER_REGISTRY = {
            "ChatGPT": ChatGPTParser,
            "chatgpt": ChatGPTParser,
        }
    return PARSER_REGISTRY


def get_parser(source: str) -> ConversationParser:
    cls = _registry().get(source) or _registry().get(source.strip())
    if cls is None:
        raise UnknownSourceError(f"No parser registered for source '{source}'.")
    return cls()


__all__ = [
    "ConversationParser",
    "ParsedConversation",
    "ParsedMessage",
    "ParseResult",
    "UnknownSourceError",
    "get_parser",
]

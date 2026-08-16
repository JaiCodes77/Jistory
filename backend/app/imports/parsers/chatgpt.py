from pathlib import Path

from app.imports.chatgpt.parser import parse_chatgpt_export
from app.imports.parsers.base import ConversationParser, ParseResult


class ChatGPTParser(ConversationParser):
    source = "ChatGPT"

    def parse(self, import_dir: Path) -> ParseResult:
        return parse_chatgpt_export(import_dir)

from pathlib import Path

from app.imports.claude.parser import parse_claude_export
from app.imports.parsers.base import ConversationParser, ParseResult


class ClaudeParser(ConversationParser):
    source = "Claude"

    def parse(self, import_dir: Path) -> ParseResult:
        return parse_claude_export(import_dir)

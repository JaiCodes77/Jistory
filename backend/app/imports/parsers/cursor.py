from pathlib import Path

from app.imports.cursor.parser import parse_cursor_import
from app.imports.parsers.base import ConversationParser, ParseResult


class CursorParser(ConversationParser):
    source = "Cursor"

    def parse(self, import_dir: Path) -> ParseResult:
        return parse_cursor_import(import_dir)

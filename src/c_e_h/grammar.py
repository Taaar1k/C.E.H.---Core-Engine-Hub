"""Grammar engine for structured output.

Provides GBNF grammar definitions and a GrammarEngine class for
compiling, validating, and parsing structured outputs.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predefined GBNF Grammars
# ---------------------------------------------------------------------------

TOOL_CALL_GRAMMAR: str = r"""\
root ::= "{" ws "\"name\":" ws tool_name ws "," ws "\"arguments\":" ws object ws "}"
tool_name ::= "\"" ([a-z_]*) "\""
object ::= "{" ws (pair ws ("," ws pair)*)? "}"
pair ::= "\"" string "\":" ws value
value ::= string | number | object | array | boolean | null
string ::= "\"" ([^"\\]|\\.)* "\""
number ::= "-"? ([0-9]+ | ([0-9]+ "." [0-9]* | [0-9]* "." [0-9]+)) ([eE] [-+]? [0-9]+)?
array ::= "[" ws (value ws ("," ws value)*)? "]"
boolean ::= "true" | "false"
null ::= "null"
ws ::= ([ \t\n] ws)?
"""

PLAIN_TEXT_GRAMMAR: str = r"""\
root ::= (any_char)*
any_char ::= .
"""

DECISION_GRAMMAR: str = r"""\
root ::= "{" ws "\"action\":" ws string ws "," ws "\"reason\":" ws string ws "}"
string ::= "\"" ([^"\\]|\\.)* "\""
ws ::= ([ \t\n] ws)?
"""


# ---------------------------------------------------------------------------
# Grammar Engine
# ---------------------------------------------------------------------------

class GrammarEngine:
    """Compiles, validates, and parses structured outputs using GBNF grammars."""

    @staticmethod
    def compile_grammar(grammar_str: str) -> str:
        """Compile a GBNF grammar string.

        Preprocesses the grammar by:
        - Stripping comment lines starting with //
        - Trimming whitespace

        Args:
            grammar_str: Raw GBNF grammar string.

        Returns:
            Cleaned grammar string.
        """
        lines = grammar_str.splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if stripped:
                cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def validate_output(output: str, schema: str) -> bool:
        """Validate output against a schema description.

        Args:
            output: The output string to validate.
            schema: Schema name — "tool_call", "decision", or "json".

        Returns:
            True if output matches schema, False otherwise.
        """
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return False

        if schema == "tool_call":
            return (
                isinstance(data, dict)
                and "name" in data
                and isinstance(data["name"], str)
                and "arguments" in data
                and isinstance(data["arguments"], dict)
            )
        if schema == "decision":
            return (
                isinstance(data, dict)
                and "action" in data
                and isinstance(data["action"], str)
                and "reason" in data
                and isinstance(data["reason"], str)
            )
        if schema == "json":
            return isinstance(data, (dict, list, str, int, float, bool, type(None)))

        logger.warning("Unknown schema schema=%s", schema)
        return False

    @staticmethod
    def parse_tool_call(output: str) -> Optional[Dict[str, Any]]:
        """Parse output as a tool call JSON.

        Args:
            output: The output string to parse.

        Returns:
            Parsed dict with "name" and "arguments" keys, or None if invalid.
        """
        if not GrammarEngine.validate_output(output, "tool_call"):
            return None
        try:
            return json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def parse_decision(output: str) -> Optional[Dict[str, Any]]:
        """Parse output as a decision JSON.

        Args:
            output: The output string to parse.

        Returns:
            Parsed dict with "action" and "reason" keys, or None if invalid.
        """
        if not GrammarEngine.validate_output(output, "decision"):
            return None
        try:
            return json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return None

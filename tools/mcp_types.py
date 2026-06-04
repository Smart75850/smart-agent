"""MCP protocol types — tool definitions, results, and retry strategies."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class MCPTool:
    """An MCP-compliant tool definition with JSON Schema input."""

    name: str
    description: str
    input_schema: dict
    handler: Optional[Callable] = None

    def to_mcp_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPToolResult:
    """Result from executing an MCP tool."""

    content: list[dict] = field(default_factory=list)
    is_error: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "isError": self.is_error,
            "metadata": self.metadata,
        }


@dataclass
class RetryStrategy:
    """A single strategy in a retry chain for platform operations."""

    name: str
    max_attempts: int = 1
    delay_seconds: float = 0.0
    use_cdp: bool = False
    use_tls_rotate: bool = False
    handler: Optional[Callable] = None

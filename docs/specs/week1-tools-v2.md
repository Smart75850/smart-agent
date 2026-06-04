# Smart Agent v2 - Week 1 Implementation Spec

> Executor: Claude Code CLI  
> Brain LLM: DeepSeek V4 Pro  
> Protocol: Anthropic MCP Standard  

## Scope

- P0-1: Retry Policy - per-platform self-healing chains
- P0-2: MCP Tool Registry - unified platform interfaces

## Files to Create

All new files under `tools/` directory. Existing scripts in `base/` stay UNCHANGED.

### File 1: `tools/__init__.py`

```python
"""Smart Agent v2 - MCP-compliant tool system and retry engine."""
```

### File 2: `tools/mcp_types.py`

Define MCPTool, MCPToolResult, RetryStrategy dataclasses.
See full code in this spec - implement as described.

### File 3: `tools/registry.py`

ToolRegistry class + 7 platform handlers + 7 MCP tool definitions.
Use lazy imports to wrap existing base/ scripts without modifying them.

### File 4: `tools/retry_policy.py`

RetryPolicy class + per-platform retry chains (XHS/Douyin have CDP fallback).

### File 5: `tests/test_tools_v2.py`

10 unit tests covering types, registry, retry policy, platform chains.

---

## Key Implementation Details

### registry.py Handlers
Each handler wraps an existing base/ script. IMPORTANT: inspect actual function
signatures in base/ and adapt. Expected structure:

- base/xhs_http.py: post_note(title, content, images, tags)
- base/douyin_http.py: post_video(video_path, description, hashtags)
- base/bilibili_http.py: post_dynamic(content, post_type)
- base/zhihu_http.py: post_article(title, content, topics)
- base/kuaishou_http.py: post_video(video_path, caption)
- base/weibo_http.py: post_weibo(content, images)
- base/tieba_http.py: post_thread(title, content)

If actual imports differ, adapt accordingly.

### retry_policy.py Chains
- XHS: http(2次) -> CDP fallback -> 60s delay retry
- Douyin: http(2次) -> TLS rotate -> CDP fallback
- Other 5: http direct (3次)
- All use lazy handler resolution to avoid circular imports

### Tests
10 test cases:
1. MCPTool creation
2. MCPToolResult defaults
3. RetryStrategy defaults
4. Register 7 platforms
5. Correct tool names
6. MCP JSON format
7. Unknown tool error
8. First strategy succeeds
9. Fallback chain
10. All strategies fail + attempt count

---

## Acceptance Criteria

| AC | Criteria | Verify |
|----|----------|--------|
| 1 | 7 platforms registered | len(list_tools()) == 7 |
| 2 | JSON Schema valid | input_schema.type == "object" |
| 3 | Retry per platform | get_retry_for(p) not empty |
| 4 | XHS/Douyin CDP fallback | strategy names check |
| 5 | Attempts counted | test_all_fail retry_count |
| 6 | No base/ changes | git diff --stat |
| 7 | All tests pass | pytest -v |
| 8 | Clean imports | python -c "from tools import ..." |

---

## Instructions

Read this spec. Implement files 1-5. 
Inspect base/ imports before writing handlers.
Run pytest. Fix failures. Report back.

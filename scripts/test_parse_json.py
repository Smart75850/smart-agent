"""Test _parse_json robustness."""
import sys
sys.path.insert(0, ".")

from src.orchestrator.agents.base import BaseAgent

p = BaseAgent._parse_json

# Test 1: normal JSON
assert p('{"a": 1}') == {"a": 1}
print("Test 1 OK: normal JSON")

# Test 2: markdown code block with json tag
assert p('```json\n{"a": 1}\n```') == {"a": 1}
print("Test 2 OK: markdown json block")

# Test 3: markdown code block without tag
assert p('```\n{"b": 2}\n```') == {"b": 2}
print("Test 3 OK: markdown block")

# Test 4: extra text before and after JSON
assert p('here is result: {"x": "y"} end') == {"x": "y"}
print("Test 4 OK: extra text")

# Test 5: trailing comma in object
assert p('{"a": 1,}') == {"a": 1}
print("Test 5 OK: trailing comma")

# Test 6: trailing comma in array
assert p('["a", "b",]') == ["a", "b"]
print("Test 6 OK: trailing comma array")

# Test 7: nested objects
assert p('{"items": [{"k": "v"}]}') == {"items": [{"k": "v"}]}
print("Test 7 OK: nested")

# Test 8: multi-trailing comma
assert p('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}
print("Test 8 OK: multi trailing comma")

# Test 9: empty object
assert p("{}") == {}
print("Test 9 OK: empty object")

# Test 10: real-world DeepSeek response
sample = """当然可以，这是分析结果：
{"summary": "test summary", "items": [{"name": "product", "score": 85}]}"""
parsed = p(sample)
assert parsed["summary"] == "test summary"
assert len(parsed["items"]) == 1
print("Test 10 OK: real-world sample")

# Test 11: just array
assert p('["a", "b"]') == ["a", "b"]
print("Test 11 OK: array")

print()
print("ALL 11 TESTS PASSED")

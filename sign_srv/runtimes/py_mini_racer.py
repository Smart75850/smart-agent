"""Python V8 运行时封装（py_mini_racer）。

进程内执行 JS，适合 10KB-50KB 的标准化签名 JS。
"""

import json
import py_mini_racer


class V8Runtime:
    def __init__(self, js_code: str):
        self._ctx = py_mini_racer.MiniRacer()
        self._ctx.eval(js_code)

    def call(self, func_name: str, *args) -> str:
        result = self._ctx.call(func_name, *args)
        if isinstance(result, str):
            return result
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    def eval(self, js_code: str):
        self._ctx.eval(js_code)

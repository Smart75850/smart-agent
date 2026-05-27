"""Node.js 桥接运行时封装（execjs）。

通过 subprocess 调用本地 Node.js，适合 50KB+ 的复杂混淆 JS。
"""

import execjs


class NodeRuntime:
    def __init__(self, js_code: str):
        self._ctx = execjs.compile(js_code)

    def call(self, func_name: str, *args):
        return self._ctx.call(func_name, *args)

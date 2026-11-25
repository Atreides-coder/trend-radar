"""AgentRunner：Pipeline 和"智能层"之间的边界。

Python 是 Orchestrator：准备输入、校验输出、写数据库。
Runner 只做一件事：拿到 prompt + 输入数据，返回符合 schema 的 dict。
它不接触数据库，也不控制流程。

目前只有 CodexRunner。以后要加 ClaudeRunner / API provider，实现同一个 run() 即可。
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field


class RunnerError(RuntimeError):
    """单次调用失败（超时、输出不合法、临时错误）——调用方可重试或跳过这一批。"""


class FatalRunnerError(RuntimeError):
    """重试也没用的错误（没安装、没登录、模型名错误、额度用完）——整个阶段应立即停止。"""


@dataclass
class RunnerUsage:
    calls: int = 0
    failed_calls: int = 0
    input_tokens: int = 0            # 含 cached_input_tokens
    cached_input_tokens: int = 0
    output_tokens: int = 0           # 含 reasoning_output_tokens
    reasoning_output_tokens: int = 0
    tool_events: int = 0             # 模型执行命令 / 调用工具的次数，Fast Filter 里应该是 0
    web_searches: int = 0            # 联网搜索次数（只有 Research 会用）
    usage_reported: bool = False     # runner 是否真的拿到了 token 用量
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class AgentRunner:
    name = "base"

    def __init__(self, model: str):
        self.model = model
        self.usage = RunnerUsage()

    def run(self, task: str, prompt: str, input_data, schema: dict) -> dict:
        """返回符合 schema 的 dict。必须线程安全。"""
        raise NotImplementedError


def require_env(env_var: str) -> str:
    """模型配置只从 .env 读，代码里不写死任何型号，也不依赖 Codex 自己记住的上次选择。"""
    value = os.environ.get(env_var, "").strip()
    if not value:
        raise FatalRunnerError(f"环境变量 {env_var} 未设置，请在 .env 中配置")
    return value

"""CodexRunner：通过 `codex exec` 非交互调用 Codex（使用 ChatGPT 登录，不需要 API key）。

每次调用尽量接近一次"结构化模型调用"，而不是一个自由探索的 Agent：
  --output-schema       用 JSON Schema 约束最终输出
  --sandbox read-only   不能写任何文件
  -C <空的临时目录>     工作目录里什么都没有，没有 repo 可扫
  --ignore-user-config  不加载用户的 MCP server / 插件 / 默认模型 / priority 档
  --ephemeral           不保存 session
prompt 走 stdin，最终结果写到 -o 指定的文件，事件流（含 token 用量）以 JSONL 打到 stdout。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import AgentRunner, FatalRunnerError, RunnerError, require_env

log = logging.getLogger("trend_radar.codex")

INSTALL_HINT = "npm install -g @openai/codex   然后运行: codex login"

_GUARD = (
    "这是一个纯判断任务。你需要的全部信息都在下面的 <input> 里。"
    "不要运行命令，不要读取或修改任何文件，不要联网搜索。直接返回符合输出 schema 的 JSON。"
)

_GUARD_SEARCH = (
    "你需要的主要材料都在下面的 <input> 里。你可以使用联网搜索来核实和补充，但不要运行命令，"
    "不要读取或修改任何文件。完成后直接返回符合输出 schema 的 JSON。"
)

# 出现这些说明重试没有意义
_FATAL = re.compile(
    r"not logged in|please (log ?in|login)|unauthorized|\b401\b|usage limit|"
    r"quota|model .{0,60}(not (supported|found|available)|does not exist)|unknown model",
    re.IGNORECASE,
)
# 这些 item 类型是正常的；其余（command_execution、mcp_tool_call、web_search 等）算工具调用
_PASSIVE_ITEMS = {"agent_message", "reasoning", "error", "web_search"}


class CodexRunner(AgentRunner):
    name = "codex"

    @classmethod
    def from_env(cls, codex_cfg: dict) -> "CodexRunner":
        """模型和推理强度必须在 .env 里显式配置（CODEX_MODEL / CODEX_REASONING_EFFORT）。

        每次 codex exec 都会显式带上 -m 和 model_reasoning_effort，并且 --ignore-user-config，
        所以无人值守运行时用什么模型是完全确定的，和 Codex Desktop / CLI 上次选了什么无关。
        """
        return cls(
            model=require_env("CODEX_MODEL"),
            reasoning_effort=require_env("CODEX_REASONING_EFFORT"),
            timeout_seconds=codex_cfg.get("timeout_seconds", 900),
            binary=codex_cfg.get("binary", "codex"),
        )

    def __init__(self, model: str, reasoning_effort: str, timeout_seconds: int = 900,
                 binary: str = "codex"):
        super().__init__(model)
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout_seconds
        self.binary = shutil.which(binary) or shutil.which(str(Path(binary).expanduser()))
        if not self.binary:
            raise FatalRunnerError(f"找不到 Codex CLI（{binary}）。安装: {INSTALL_HINT}")
        self.version = self._check("--version")
        status = self._check("login", "status")
        if "logged in" not in status.lower() or "not logged in" in status.lower():
            raise FatalRunnerError(f"Codex 未登录（{status or '无输出'}）。请运行: codex login")
        self.login_status = status

    def _check(self, *args: str) -> str:
        try:
            p = subprocess.run([self.binary, *args], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise FatalRunnerError(f"无法运行 codex {' '.join(args)}: {e}") from e
        return (p.stdout + p.stderr).strip().splitlines()[0] if (p.stdout + p.stderr).strip() else ""

    def run(self, task: str, prompt: str, input_data, schema: dict, web_search: bool = False,
            reasoning_effort: str | None = None) -> dict:
        """web_search=True 时允许模型联网搜索（仅 Research 使用），其余限制不变：只读沙箱、空目录、不改任何文件。"""
        guard = _GUARD_SEARCH if web_search else _GUARD
        full_prompt = (
            f"{prompt}\n\n---\n{guard}\n\n<input>\n"
            + json.dumps(input_data, ensure_ascii=False, indent=1)
            + "\n</input>\n"
        )
        log.debug("CODEX INPUT [%s]\n%s", task, full_prompt)

        with tempfile.TemporaryDirectory(prefix=f"trend-radar-{task}-") as tmp:
            schema_path, out_path = Path(tmp, "schema.json"), Path(tmp, "result.json")
            workdir = Path(tmp, "empty")
            workdir.mkdir()
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            cmd = [
                self.binary, *(["--search"] if web_search else []), "exec",
                "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                "--sandbox", "read-only", "--color", "never",
                "-C", str(workdir),
                "-m", self.model,
                "-c", f'model_reasoning_effort="{reasoning_effort or self.reasoning_effort}"',
                "--output-schema", str(schema_path),
                "-o", str(out_path),
                "--json", "-",
            ]
            try:
                proc = subprocess.run(cmd, input=full_prompt, capture_output=True, text=True,
                                      timeout=self.timeout, cwd=workdir)
            except subprocess.TimeoutExpired as e:
                self._fail()
                raise RunnerError(f"codex exec 超时（{self.timeout}s）") from e
            except OSError as e:
                self._fail()
                raise FatalRunnerError(f"无法启动 codex: {e}") from e

            errors = self._read_events(proc.stdout)
            log.debug("CODEX EVENTS [%s] exit=%d\n%s", task, proc.returncode, proc.stdout)
            if proc.returncode != 0:
                self._fail()
                detail = (" | ".join(errors) or proc.stderr.strip() or proc.stdout.strip())[-600:]
                msg = f"codex exec exit={proc.returncode}: {detail}"
                log.warning(msg)
                raise (FatalRunnerError if _FATAL.search(detail) else RunnerError)(msg)

            text = out_path.read_text(encoding="utf-8") if out_path.exists() else ""

        log.debug("CODEX OUTPUT [%s]\n%s", task, text)
        if not text.strip():
            self._fail()
            raise RunnerError("codex exec 没有返回最终消息")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            self._fail()
            raise RunnerError(f"JSON 解析失败: {e}") from e

    def _read_events(self, stdout: str) -> list[str]:
        """从 JSONL 事件流里累计 token 用量、统计工具调用，返回错误信息。"""
        errors: list[str] = []
        usage, tools, searches = None, 0, 0
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type", "")
            if kind == "turn.completed":
                usage = ev.get("usage") or usage
            elif kind == "item.completed" and ev.get("item", {}).get("type") == "web_search":
                searches += 1
            elif kind == "item.completed" and ev.get("item", {}).get("type") not in _PASSIVE_ITEMS:
                tools += 1
            elif kind in ("error", "turn.failed"):
                errors.append(str(ev.get("message") or ev.get("error") or ev)[:400])
        with self.usage._lock:
            self.usage.calls += 1
            self.usage.tool_events += tools
            self.usage.web_searches += searches
            if usage:
                self.usage.usage_reported = True
                self.usage.input_tokens += usage.get("input_tokens", 0)
                self.usage.cached_input_tokens += usage.get("cached_input_tokens", 0)
                self.usage.output_tokens += usage.get("output_tokens", 0)
                self.usage.reasoning_output_tokens += usage.get("reasoning_output_tokens", 0)
        if tools:
            log.warning("Codex 在这次调用里执行了 %d 次工具/命令（本应为 0）", tools)
        return errors

    def _fail(self):
        with self.usage._lock:
            self.usage.failed_calls += 1

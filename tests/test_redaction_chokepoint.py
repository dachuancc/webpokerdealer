"""结构约束：牌与凭据只能经收口点离开服务端（守护 D3 / D12）。

`test_leak_fuzz.py` 从**行为**上守：跑真实牌局，检查真正下发出去的 payload。
本文件从**代码形状**上守：即使某条路径现在没被跑到，也不允许出现"能碰到底牌或凭据"的写法。
两者互补——行为测试防"现在漏"，结构测试防"以后漏"（比如顺手加个调试字段、加条新路由）。

规则（作用于 `src/webpokerdealer/web/`，也就是唯一的下发层）：

* R1 不得访问带牌的内部属性：``hole`` / ``deck`` / ``burned`` / ``_result``。
  底牌与牌堆只在 `game/` 里存在，对外只能经 `board_state()` / `player_state()`。
* R2 不得整体序列化对象（``asdict`` / ``astuple`` / ``vars`` / ``__dict__``）——
  那是绕过视图过滤的旁路。
* R3 秘密字段（``pin`` / ``host_token`` / ``token``）只允许在"把凭据发给该发的那一方"
  的几个入口里访问（D7 / D12）。
* R4 状态出口唯一：`board_state()` / `player_state()` 只允许在 `ws.py::Hub.send_state`
  里调用——新增一条返回原始状态的 HTTP 路由就等于把 PIN 摊牌给所有人。

改这些规则不是不行，但必须是**有意识的**改动：真需要放宽时改这里的白名单，
别把测试删掉。
"""

from __future__ import annotations

import ast
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
WEB_DIR = BASE / "src" / "webpokerdealer" / "web"

# R1：game/ 里带牌的内部属性，web 层一律不许碰。
CARD_ATTRS = frozenset({"hole", "deck", "burned", "_result"})

# R2：整体序列化 = 绕过视图过滤。
SERIALIZE_NAMES = frozenset({"asdict", "astuple", "vars"})
SERIALIZE_ATTRS = frozenset({"__dict__", "asdict", "astuple"})

# R3：秘密字段 + 允许访问它们的（所在函数, 属性名）。
SECRET_ATTRS = frozenset({"pin", "host_token", "token"})
SECRET_ALLOWLIST = frozenset(
    {
        # 创建牌桌：把 PIN 和 host_token 交给创建者（他自己就是主持人）。
        ("create_table", "pin"),
        ("create_table", "host_token"),
        # 换设备：用 PIN 换 host_token。
        ("host_auth", "pin"),
        ("host_auth", "host_token"),
        # 入座：把玩家自己的 token 交给他自己。
        ("join_table", "token"),
    }
)

# R4：状态出口唯一。
STATE_BUILDERS = frozenset({"board_state", "player_state"})
STATE_BUILDER_ALLOWLIST = frozenset({("ws.py", "send_state")})


# ------------------------------------------------------------------- 解析工具


def _web_modules() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text())) for path in sorted(WEB_DIR.rglob("*.py"))]


def _attr_references(tree: ast.Module) -> list[tuple[int, str]]:
    """收集"按名字取属性"的写法：``x.name`` 与 ``getattr(x, "name")``。"""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            found.append((node.lineno, node.attr))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            found.append((node.lineno, node.args[1].value))
    return found


def _functions(tree: ast.Module) -> list[tuple[ast.AST, int, int, str]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            end = node.end_lineno or node.lineno
            out.append((node, node.lineno, end, node.name))
    return out


def _enclosing_function(tree: ast.Module, lineno: int) -> str | None:
    """最内层包含该行的函数名（嵌套函数取最内层）。"""
    candidates = [
        (start, name)
        for _node, start, end, name in _functions(tree)
        if start <= lineno <= end
    ]
    return max(candidates)[1] if candidates else None


def _call_receivers(tree: ast.Module, names: frozenset[str]) -> list[tuple[int, str]]:
    """`x.foo(...)` 形式的方法调用，返回 (行号, 方法名)。"""
    return [
        (node.lineno, node.func.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in names
    ]


# ------------------------------------------------------------------ 守卫本身


def test_guard_scans_the_real_web_layer():
    """防止路径写错，让整个文件变成"扫了个空目录还全绿"。"""
    names = {path.name for path, _ in _web_modules()}
    assert {"ws.py", "routes.py"} <= names, f"没扫到预期的 web 模块，实际：{sorted(names)}"


def test_detector_works_on_a_known_bad_sample():
    """正向对照：扫描器必须真能认出一个明显违规的写法。"""
    tree = ast.parse('def leak(table):\n    log.debug(table.deck)\n    return getattr(table, "hole")\n')
    found = {attr for _line, attr in _attr_references(tree)}
    assert {"deck", "hole"} <= found, f"扫描器漏掉了违规写法，只认出：{sorted(found)}"


# --------------------------------------------------------------------- 规则


def test_web_layer_never_touches_card_bearing_attributes():
    """R1：web 层不得直接碰 hole / deck / burned / _result。"""
    problems = [
        f"{path.relative_to(BASE)}:{lineno} 访问了 {attr!r}"
        for path, tree in _web_modules()
        for lineno, attr in _attr_references(tree)
        if attr in CARD_ATTRS
    ]
    assert not problems, (
        "web 层出现了直接触碰牌相关内部属性的写法；底牌/牌堆只能经 "
        "board_state() / player_state() 出口：\n  " + "\n  ".join(problems)
    )


def test_web_layer_never_serializes_objects_wholesale():
    """R2：不得整体序列化对象（等于绕过视图过滤）。"""
    problems = []
    for path, tree in _web_modules():
        rel = path.relative_to(BASE)
        for lineno, attr in _attr_references(tree):
            if attr in SERIALIZE_ATTRS:
                problems.append(f"{rel}:{lineno} 使用了 {attr!r}")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in SERIALIZE_NAMES
            ):
                problems.append(f"{rel}:{node.lineno} 调用了 {node.func.id}()")
    assert not problems, (
        "整体序列化会一次性带出牌堆与所有人的底牌，属于绕过过滤的旁路：\n  "
        + "\n  ".join(problems)
    )


def test_secret_fields_only_leave_through_their_issuing_endpoints():
    """R3：PIN / host_token / 玩家 token 只在发放它们的入口里出现（D7 / D12）。"""
    problems = []
    for path, tree in _web_modules():
        for lineno, attr in _attr_references(tree):
            if attr not in SECRET_ATTRS:
                continue
            owner = _enclosing_function(tree, lineno)
            if (owner, attr) not in SECRET_ALLOWLIST:
                problems.append(f"{path.relative_to(BASE)}:{lineno} 在 {owner}() 里访问了 {attr!r}")
    assert not problems, (
        "秘密字段只能发给它该发的那一方（玩家拿自己的 token，主持人拿 PIN/host_token）：\n  "
        + "\n  ".join(problems)
    )


def test_state_builders_are_only_called_from_the_hub():
    """R4：下发状态的出口只有 ws.py 的 Hub.send_state。"""
    problems = [
        f"{path.relative_to(BASE)}:{lineno} 调用了 {builder}()"
        for path, tree in _web_modules()
        for lineno, builder in _call_receivers(tree, STATE_BUILDERS)
        if (path.name, _enclosing_function(tree, lineno)) not in STATE_BUILDER_ALLOWLIST
    ]
    assert not problems, (
        "新增的返回原始状态的出口等于把底牌/PIN 直接对外，请改用 Hub.send_state：\n  "
        + "\n  ".join(problems)
    )

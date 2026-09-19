# AGENTS.md — webpokerdealer

给 AI 编码助手（pi 等）的项目上下文。**开始改动前，先读 `docs/ROADMAP.md`（进度与下一步）
和 `docs/DECISIONS.md`（已定的技术决策，勿轻易推翻）。**

## 这是什么

家庭德州扑克**发牌助手**：一台平板当"公牌桌"（显示公共牌、控制发牌进度），
每人用自己的手机入座、只看自己的底牌。不洗牌、不发牌、不记录筹码。
浏览器运行，最终以单容器 Docker 部署到 NAS。

## 技术栈

- Python 3.11+ / FastAPI / Uvicorn，WebSocket 做实时同步
- Jinja2 模板 + 原生 JS + 手写 CSS（**无前端构建、无 npm**）
- 依赖与虚拟环境用 `uv` 管理
- 状态全在内存，无数据库（见 `DECISIONS.md` D2）

## 目录结构

```
src/webpokerdealer/
├── main.py            # FastAPI app 工厂 + 入口
├── config.py          # 环境变量配置（WPD_*）
├── game/
│   ├── cards.py       # Card / Deck（secrets 洗牌）
│   ├── table.py       # Table 状态机 + 视图过滤（核心）
│   └── rooms.py       # 房间注册表（进程级单例 rooms）
├── web/
│   ├── routes.py      # HTTP 路由 + QR 生成
│   └── ws.py          # WebSocket Hub（按角色下发过滤后的状态）
├── templates/         # base / index / board / player
└── static/            # css/app.css, js/common|index|board|player.js
tests/                 # test_cards / test_table / test_web
```

## 常用命令

```bash
uv sync                                              # 安装依赖
uv run uvicorn webpokerdealer.main:app --reload --host 0.0.0.0 --port 8000
uv run pytest                                        # 跑测试（改动后必须全绿，基线 90；slow 默认跳过）
uv run pytest -m slow                                # 穷举 5 张手牌空间（约 15 秒，验证评估器与参照双射）
docker compose up -d --build                         # 本地验证容器
```

## 运行与调试

- 开发：`uv run uvicorn webpokerdealer.main:app --reload --host 0.0.0.0 --port 8000`
- 实际开玩：**去掉 `--reload`**（它会在改代码时重启进程，清空内存中的牌桌）
- 手机/平板用 `http://<本机局域网IP>:8000` 访问；平板「创建牌桌」当公牌桌，手机扫码入座
- 诊断连接：uvicorn 日志里带时间戳的 `ws open/close/reject`（`reason=...`）

## 当前状态与下一步

M0 + M1 已完成并**真机三设备联调验证**（底牌隔离、发牌流程、断线重连均正常）。
下一步见 `docs/ROADMAP.md` 的「下一步」；动手前先读 `docs/DECISIONS.md`。
**动手造轮子前先看 `docs/PRIOR-ART.md`**（同类项目 / 可借鉴项 / 许可证边界）：
哪些现成方案能参考、哪些只能读思路不能抄代码，那份文档里有结论。

## 已知坑

- **`--reload` 会清空牌局**：状态在内存（D2），代码一改就重启 → 牌桌/token 全失效。
  客户端会收到 `reason=table_missing` 并停止重连、提示重新建桌。
- **浏览器 JS 缓存**：无构建步骤，改 `static/js/*.js` 后必须**强制刷新**，否则跑的是旧代码。
- **iPhone 手输 IP 常失败**：Safari 会把 `192.168.x.x:8000` 当搜索词。让玩家**扫码**，
  或手动输入完整 `http://` 前缀。
- **别用 `pkill -f "uvicorn webpokerdealer"` 停开发服务**：`-f` 匹配整条命令行，而执行这条命令的
  shell 自己命令行里就含这种字串 → **会把服务和自己一起杀掉**，后半条命令的输出也一并没了。
  改用**按端口反查 PID**：
  ```bash
  kill $(ss -ltnp | grep ':8000' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | head -1)
  ```
  （容器用 `docker compose stop` 就行，不涉及这个问题。）

## 核心不变量（改动务必守护）

- **牌堆与底牌只存在于服务器**。对外只有两个出口：
  `Table.board_state()`（公牌桌视图）和 `Table.player_state(id)`（玩家视图）。
- 公牌桌在**摊牌前**看不到任何底牌；玩家只能看到**自己的**底牌。
- 摊牌时只揭示**未弃牌**玩家。
- 玩家身份用随机 `token`（入座时下发，WS 连接时校验），不设账号密码。
- 公牌桌控制面用 `host_token` 鉴权（创建时下发，WS 连接时校验）；`pin` 仅用于换设备时换取
  host_token，且只下发给公牌桌（见 D12）。
- 洗牌必须用 `secrets.SystemRandom`（测试可注入 `random.Random(seed)`）。
- **上一局、弃牌者、中途入座者的底牌都不得出现在任何视图与历史里**（见 D11）。

> 守护这些不变量的测试分两层（D18）：`tests/test_leak_fuzz.py` 从**行为**上守（随机跑牌局、
> 检查真正下发的 payload），`tests/test_redaction_chokepoint.py` 从**代码形状**上守
> （禁止 web 层碰 `hole`/`deck`，禁止整体序列化，状态出口只允许 `Hub.send_state`）。
> 攻这两块之前先读读它们的文件头。

## 代码约定

- 领域逻辑放 `game/`，**不要**让 `game/` 依赖 web 层。
- 任何破坏上述不变量的改动都要**先加/改测试**，再改实现。
- 前端不引入构建步骤；新 JS 直接放 `static/js/`，由模板 `<script>` 引入。
- 测试里禁止无界的 `receive_json()` 循环（会挂死套件）；`pytest-timeout` 已设 30s。
- **验证要有明确结论**：收尾时说明哪些测试全绿、手动验证了哪条路径（如真机多设备的哪一步）。
  **没有验证 = 没做完**，不要用「应该没问题」结案。
- **提交信息**：用中文，见下方「提交信息规范」。

## 提交信息规范

**先分两类**：看这次改动是否对应 `docs/ROADMAP.md` 里的里程碑编号。

| 类别 | 格式 | 例子 |
|---|---|---|
| **里程碑功能** | `M<编号>: 简述` | `M3-1: 摊牌自动比牌与获胜提示` |
| **其他** | `<类型>: 简述`（类型见下表） | `文档：部署方案定档（D15 + DEPLOY §0）` |

**类型表**（只用这几个，不要自造）：

| 类型 | 用于 |
|---|---|
| `文档` | 改 `docs/`、`README.md`、`AGENTS.md` |
| `配置` | 依赖、环境变量、构建、Docker |
| `工具` | 开发 / 运维工具链（脚本、脚手架） |
| `重构` | 不改行为的结构调整 |
| `修复` | 修 bug |
| `测试` | 仅增改测试（不含功能改动） |

**正文**：用 `-` 列要点，写**为什么**而不只是做了什么；行为变化要说清（含兼容性影响）。
涉及已定架构决策时**引用编号**（如 `D12`），方便回溯 `docs/DECISIONS.md`。

**规则**
- 用中文，主题行简短（≤ 约 40 字），不以句号结尾。
- **功能开发一律用 `M<n>:`**，编号是 `ROADMAP.md` 的锚点，关系到能否按编号回溯进度。
- 一次提交只做一件事；**文档改动不要混进功能提交**。
- **不追溯历史**：旧提交里的异类写法保留原样，只管新提交按上表执行。

## 红线

- **仅供家庭娱乐**：不实现真钱、赔率、赌博相关功能。
- 不把密钥/token 写入仓库；`.env` 已在 `.gitignore`。
- 状态无持久化是**有意设计**，不要擅自加数据库（先改 `DECISIONS.md`）。

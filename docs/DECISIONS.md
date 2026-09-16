# DECISIONS — webpokerdealer

记录已定的技术决策与理由。**开工前先读，勿轻易推翻**；要改先在此讨论。

## D1 技术栈：Python + FastAPI + WebSocket + 原生前端

- 多设备实时同步（公牌桌 ↔ 各手机）用 WebSocket 最直接
- 单进程同时提供 HTML / REST / WS，**无前端构建步骤**，Docker 部署最省事
- 与个人既有 uv/Python 习惯一致
- 备选（Node/TS + Socket.IO）被否：需要 npm 构建链，对家庭小工具过重

## D2 状态全在内存，无数据库

- 家庭牌局是瞬时的，容器重启丢局可接受
- 免去 DB 迁移、卷挂载、备份等运维负担
- 房间注册表 `game/rooms.py::rooms` 是进程级单例
- 若未来要持久化历史牌局，再加 SQLite（Django 之外的轻量方案）

## D3 服务端权威 + 按角色过滤视图（核心安全不变量）

- 牌堆/底牌只存服务器；`Table.board_state()` 与 `Table.player_state(id)` 是两个出口
- 公牌桌在**摊牌前看不到任何底牌**；玩家只能看到自己的底牌
- 摊牌时只揭示**未弃牌**玩家
- 任何改动都必须有守护测试（`tests/test_table.py`、`tests/test_web.py`）

## D4 洗牌用 `secrets.SystemRandom`

- 操作系统级 CSPRNG，无需第三方库
- 测试可注入 `random.Random(seed)` 得到确定性序列
- 实现真实发牌顺序：从庄家左手起逐张发两轮；翻牌/转牌/河牌前各烧一张

## D5 只发牌，不记录筹码与下注

- 筹码/下注在实体桌上完成，程序只解决"洗牌发牌"这件事
- 避免把娱乐工具做成赌博工具，也避免与实体筹码状态不同步
- 弃牌按钮仅用于"摊牌时不亮牌"

## D6 公牌桌暂不鉴权

- 家庭局域网内使用，牌桌号（4 位）+ 房间码即隐式口令
- 未来如需要，加主持人 PIN（已在 ROADMAP M2 记录）

## D7 玩家身份用随机 token，不设账号密码

- 入座时服务端发 `token`，玩家页存 localStorage，WS 连接时校验
- 容器重启 token 失效 → 前端检测到"身份校验失败"自动回到入座页
- 无需注册/登录，符合"朋友在家玩一次"的场景

## D8 烧牌照做

- 真实德州每街前烧一张（`Table.burned`），保持仪式感与真实性
- 只统计数量，不展示

## D9 前端零依赖、零构建

- Jinja2 模板 + 原生 JS（`common.js` / `board.js` / `player.js`）+ 手写 CSS
- 不引入 npm/打包器；QR 用服务端 `qrcode` 生成内联 SVG

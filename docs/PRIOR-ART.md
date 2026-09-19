# PRIOR-ART — 同类项目调研与可借鉴项

调研于 2026-09-17，来源为 GitHub 仓库搜索（关键词 + topic，含少量代码检索）。
**星数 / 活跃度是当日快照，会变**；不是代码级全量检索，结论限于本次检索范围。

**为什么要写这份文档**：确认这个工具在开源生态里的位置；把「值得学的设计 / 必须避开的坑 /
许可证边界」沉淀下来，避免只留在对话里（与仓库自描述原则一致）。

**结论先行**：
- 形态上确有近似项目，但**没找到同时满足「物理牌局 + 手机只看自己底牌 + 服务端按角色隔离
  + 自托管」四项的开源实现**。
- 最接近的 *产品* 是 `pokards`，而它恰恰在**安全模型上是反面教材**（见 §4）——
  这反过来印证了 D3（服务端权威 + 过滤视图）与 D4（CSPRNG）不是过度设计。
- 工程质量上最值得学的是 `felt`（§2.3），它的两条做法我们**尚未具备**，列在 §5。

---

## 1. 最接近的三个

| 项目 | 语言 / 星 | 像在哪 | 状态 |
|---|---|---|---|
| [`tidann/pokards`](https://github.com/tidann/pokards) | Dart / Flutter ★29 | **产品形态几乎一样**：App 扮演"发牌人"，有 Player mode（公共牌 + 自己的手牌）与 Table mode（只显示公共牌），可离线 | 2025-02 停更，**无许可证** |
| [`Tehes/poker`](https://github.com/Tehes/poker) | JavaScript ★34 | **交互流程几乎一样**：浏览器牌桌 + 扫码入座 + 每人用自己设备看底牌 + 私有视图不暴露在公共屏 + 手机/平板响应式 | 2026-09 活跃，**source-available（非开源）** |
| [`Kevin-Lalor/felt`](https://github.com/Kevin-Lalor/felt) | TypeScript ★0 | 自托管家庭局 6–9 人、手机点链接加入、**服务端按座位 redact 底牌**、可验证公平 | 2026-09 活跃，**无许可证** |

### 1.1 `Tehes/poker` —— 交互层最像

README 自述的卖点与我们高度重合：`No app install`、`QR + Link Joining`、
`Private Player Views`（"human players can join on their own devices without exposing
private information on the shared screen"）、`Responsive Design`（平板/手机/桌面）、
`Fast & Offline-Ready`。

差异：它是一套完整游戏（含筹码、边池、机器人、盲注递增），我们是**只发牌不记筹码**的助手
（D5）。它默认聊天/遥控也更重。

⚠️ **许可证**：source-available 而非开源，明确要求「公开再分发须链接原作 + 应用内署名
"Based on Poker by Tehes" + 标注为修改版」，并**禁止商用、付费托管、转售、误导性改名**。
→ **只可读思路，不可复制代码**（见 D17）。

### 1.2 `jacobhyphenated/PokerServer` —— 场景动机写得最好（MIT，可参考代码）

Java ★166，MIT，2017 停更。**REST**（非 WebSocket）家庭局服务端。

它 README 里"为什么做这个"的动机分析，几乎逐条对应我们 `AGENTS.md` 的场景描述：
家庭局里新手慢、有人不专心会抢先行动或想太久、翻错牌/发错牌要重开、**洗牌和发牌本身耗时**。
值得作为 README「为什么做这个」的写法参考。

差异：它是完整的引擎（含筹码、边池、行动顺序、合法动作），我们刻意不做这些（D5）。

### 1.3 `Kevin-Lalor/felt` —— 工程质量参考范本（0 星但水准最高）

自托管、手机加入、play-money NLHE。可读的文档很完整：`docs/FAIRNESS.md`、
`docs/ARCHITECTURE.md`、`docs/ENGINE-SPEC.md`。

它的两条核心做法我们**目前没有**，且都直接对应我们的核心不变量：

1. **单一 redact 收口点**：架构文档写明 `redact.ts` 是
   *"THE choke point. Nothing broadcasts around it"*——所有出站状态必须经过它，
   并用 **5000 手泄漏模糊测试**保证对手底牌从不出现在 payload 里。
2. **commit-reveal 洗牌链**（详见 §5.2）：服务端**提前一手**公布 `SHA256(serverSeed)`，
   发牌用 `HMAC(serverSeed, 玩家种子 | 手数)` 驱动 Fisher–Yates，牌局结束公布种子，
   附独立验证器 → **服务端也无法作弊**，玩家可离线复算。

其他细节也踩过坑、值得记：
- Fisher–Yates 用**拒绝采样**避免取模偏差；
- 玩家**名字在手牌期间冻结**（改名会让历史记录不可验证）；
- 记录用位置索引而非以名字为 key（改名/重连曾直接把记录搞坏）；
- 手牌 ID 用 `${sessionId}-${handNumber}`（`handNumber` 会重启）。

⚠️ 无许可证 → 同样只可读思路（D17）。

---

## 2. 场景 / 部署近亲

| 项目 | 说明 | 可借鉴 |
|---|---|---|
| [`LeonemZhang/Texas_Holdem`](https://github.com/LeonemZhang/Texas_Holdem) ★4 GPL-3.0 | 开源自托管 NLHE，Windows 房主 + 手机浏览器加入，支持**实体局域网或 EasyTier 虚拟局域网** | 部署形态的第三条路（§5.3）；有 CI/发布流程 |
| [`xumou89/family-poker`](https://github.com/xumou89/family-poker) | 家庭局 Node + Socket.IO：多桌大厅、断线重连 **180s 宽限**、管理后台、邀请码 | 宽限期思路；无许可证 |
| [`llllzt/poker-game`](https://github.com/llllzt/poker-game) | 局域网服务器 / P2P 双模式**自动探测**、手机横屏适配 | 无外网时的降级思路；无许可证 |
| [`floatinghotpot/casino-server`](https://github.com/floatinghotpot/casino-server) ★1165 MIT | 老牌 node + socket.io + **Redis 作消息总线**的扑克服务端 | 多进程/多桌扩展的参考坐标系（我们现在单进程 + 内存，D2） |
| [`jaxankey/Virtual-Game-Table`](https://github.com/jaxankey/Virtual-Game-Table) ★62 GPL-3.0 | 通用浏览器共享游戏桌 | 若将来要扩展别的牌类 |
| [`heute666/smart-poker-dealer`](https://github.com/heute666/smart-poker-dealer) ★14 GPL-3.0 | **硬件**路线：3D 打印机械臂发真牌（shuffler-free） | 说明"自动发牌"还有物理解法，不是我们要走的路 |

---

## 3. 可当工具 / 库用

| 项目 | 用途 |
|---|---|
| [`uoftcprg/pokerkit`](https://github.com/uoftcprg/pokerkit) ★498 MIT，活跃，Python | 牌型评估 + 状态机 + 手牌历史格式。可作为 `evaluator.py` 的**第二个独立 oracle**（见 §5.1） |
| [`treys`](https://github.com/ihendley/treys) MIT | **已采用**为 dev 依赖做差分测试，见 D16 |
| [`HenryRLee/PokerHandEvaluator`](https://github.com/HenryRLee/PokerHandEvaluator) ★517 / [`worldveil/deuces`](https://github.com/worldveil/deuces) ★623 | 评估算法对照（⚠️ `deuces` **无许可证**，见 D16/D17） |
| [`crobertsbmw/deckofcards`](https://github.com/crobertsbmw/deckofcards) ★1425 MIT | REST 发牌接口（deckofcardsapi.com）。若要拆"牌堆服务"或做测试替身可看 |

**游戏 AI / 求解器类不列入**：`TexasSolver`、`rlcard`、`openpoker` 等服务于胜率求解与
AI 训练，与本项目"只发牌"的定位无关。

---

## 4. 反面教材：`pokards` 的确定性洗牌

`lib/logic/game_creator.dart`（原样摘录）：

```dart
final digest = sha256.convert(utf8.encode(gameId)).bytes;
final seed = digest.take(5).reduce((value, element) => value * element);  // 5 字节相乘当种子
final random = Random(seed);
deck.shuffle(random);          // 所有设备各自本地算出同一副牌
```

**设计意图**：用 Game ID 当共享种子，各设备无需联网即可推演出同一副牌（所以它能离线）。

**为什么是洞**：Game ID 是**所有入座玩家都必须知道**的值（他们得输入它才能开局）。
于是任何知道这套派生方式的人，都能从 Game ID 算出**全桌底牌**——牌面保密完全依赖
"玩家不去看源码"，属于安全上的隐蔽式设计（security through obscurity）。

顺带两处实现问题：把 5 个字节**相乘**当种子派生损失熵且有碰撞；用的是非加密 PRNG。

**对我们的价值**：这是一次现成的反面验证——
- D3（服务端权威 + 按角色过滤视图）不是多余：只要牌在客户端可推演，隐私就不成立；
- D4（`secrets.SystemRandom`）也是必要的：种子的**不可猜**与**不可复现**是两件事。

---

## 5. 可借鉴项清单

### 5.1 低成本，直接强化现有不变量

1. **泄漏模糊测试**（学 felt 的 5k-hand leak fuzzer）——*建议做*
   随机跑 N 手（含中途入座、弃牌、摊牌、提前结束等状态组合），把 `board_state()`
   与每个 `player_state()` **序列化成 JSON 后遍历断言**：
   摊牌前不含任何底牌、玩家视图不含他人底牌、弃牌者不出现在摊牌结果里。
   现状：`tests/test_table.py` / `test_web.py` 只有**定向**用例，缺这种"广撒网"式不变量测试。

2. **收口点的结构性约束测试**——*建议做*
   felt 靠约定 + 测试保证没人绕过 `redact.ts`。我们的两个出口是 `board_state()` /
   `player_state()`，可以加一个测试扫描 `web/` 与模板，**禁止**在这两处之外访问
   `hole_cards`。防的是"以后顺手加个接口"这类无声破口。

3. **手牌稳定 ID**——*可选*
   felt 用 `${sessionId}-${handNumber}`，因为 `handNumber` 会重启。我们"本局回顾"目前
   按局数索引，牌桌没有 sessionId；容器重启后局数从 1 重新开始。只在本机看历史时够用，
   若将来要导出/对拍，需要稳定 ID。

4. **第三方 oracle 再加一个**——*可选*
   D16 已用 `treys` 对拍，已解决"纯手写用例查不出边界暗坑"。残留风险是"我们对拍的两边
   会不会一起错"（概率低但不是零）。`pokerkit` 是**另一套算法与另一套作者**的实现，
   可作为第二个 oracle。收益递减，按需再说。

### 5.2 大件：commit-reveal 洗牌（把 D4 从"信任服务端"升级为"可验证公平"）

现状：洗牌用 `secrets.SystemRandom`，**玩家必须信任服务端**没有偷看/挑选牌堆。
felt 的 `docs/FAIRNESS.md` 给了一份完整可抄思路（**注意：只读思路，不抄代码**）的协议：

1. **Commit**：`commit = SHA256(serverSeed)`，本手用的种子**上一手就公布哈希**；
2. **Derive**：`HMAC-SHA256(serverSeed, 玩家种子按座位顺序 join + 手数 + 块序号)`
   产生确定字节流，驱动 Fisher–Yates（**必须拒绝采样**避免取模偏差）；
3. **Deal**：左手起逐张发两轮，再翻牌/转牌/河牌；
4. **Reveal**：牌局结束公布 `serverSeed`，任何人可校验哈希并重演牌堆。

**关键坑（felt 明确记录）**：commit 必须**提前一手**铸造。
若在发牌时才生成种子（即先读到玩家种子再决定），服务端可以"生成→推演→评估→挑选"
出一个自己喜欢的牌堆，而 `SHA256(revealed) == commit` 仍然成立、验证器照样打绿钩。
felt 为此专门留了回归测试。

**顺带收益**：一旦有了每手的 reveal 记录，D2 的"可选持久化历史"与"本局回顾"就有了
可验证的数据基础。代价：协议复杂度、每手的 reveal 消息、以及一个验证器实现。

> 与本项目定位的关系：家庭娱乐局里"服务端会不会作弊"其实不是主要威胁（服务端就是
> 家里那台机器，主持人也不是庄家）。所以这属于**加分项而非必需项**，
> 排期上晚于 M4。

### 5.3 部署第三条路：虚拟局域网（补 `DEPLOY.md` §0.2）

`DEPLOY.md` §0.2 现有两条应对"外出换网/IP 会变"的路子：Pi 开热点、带旅行路由器。
`LeonemZhang/Texas_Holdem` 提供了第三条：**EasyTier / Tailscale 之类虚拟局域网**——
不需要改网络拓扑、不需要热点，设备装个客户端就同网段。代价是需要外网。
D15 的"当时未考虑的替代方案"里已提到 Tailscale / Cloudflare Tunnel，本项是把
EasyTier 一并落进 `DEPLOY.md`，供"树莓派便携"场景对比。

---

## 6. 许可证边界（→ 见 D17）

调研中大量项目**无许可证**（`pokards`、`felt`、`family-poker`、`Tehes/poker`）——
「无许可证」默认**保留所有权利**，与"开源"不是一回事。

| 类别 | 项目 | 能做什么 |
|---|---|---|
| MIT / 宽松 | `PokerServer`、`casino-server`、`pokerkit`、`treys`、`deckofcards` | 可参考，也可借用代码（须保留版权声明） |
| GPL-3.0 | `Texas_Holdem`、`Virtual-Game-Table`、`smart-poker-dealer` | 抄代码会传染 GPL。本项目是 MIT，**不要抄** |
| 无许可证 / source-available | `pokards`、`felt`、`family-poker`、`Tehes/poker` | **只能读思路，不能复制代码** |

本项目自身的许可证与第三方资源政策见 `DECISIONS.md` **D17**（MIT；牌面/音频只收
公有领域 / CC0 / 宽松许可）。

---

## 7. 本次检索没有找到的东西（负向结论）

- 没有找到同样做「**实体牌局 + 虚拟底牌发到各自手机 + 公共牌投在共享屏 + 不记筹码**」
  的开源实现。最接近的三个各差一块：`pokards` 差安全模型、`Tehes/poker` 差"不记筹码"
  且非开源、`felt` 差"不记筹码"且无许可证。
- 没有找到可直接复用的「按角色过滤牌桌视图」的实现（felt 的思路最接近，但代码不可用）。
- 没有找到把"发牌助手"当独立可复用服务（如牌堆 API）来做的主流项目——
  `deckofcardsapi` 只是通用牌堆，不含牌桌与角色概念。

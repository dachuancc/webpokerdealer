# webpokerdealer

家庭德州扑克**发牌助手**。用浏览器就能跑：一台平板放在桌子中间当"公牌桌"（显示公共牌、控制发牌进度），
每个人用自己的手机打开网页入座，只在自己的手机上看到自己的两张底牌。省去洗牌、发牌的麻烦。

## 特点

- **服务端权威**：牌堆和座位都在服务器上，每台设备只收到它该看到的信息（别人的底牌不会下发到你的手机）。
- **实时同步**：WebSocket 广播，平板点"下一轮"，所有手机立即更新。
- **零构建前端**：Jinja2 模板 + 原生 JS，一个容器同时提供页面 / API / WebSocket。
- **NAS 友好**：单容器 Docker 部署，手机 / 平板通过局域网 IP 访问。
- **每桌最多 9 人**：座满后服务端拒绝入座（公牌桌显示「座位 X/9」）。
- **摊牌自动比牌**：摊牌时显示各人牌型并高亮赢家（平局并列显示），只判断牌型，不涉及筹码。
- **可自定义外观**：牌桌背景、牌背颜色、四色牌（每台设备各自记忆）。
- **可选精美牌面**：内置一套公有领域的矢量扑克牌（Byron Knoll），设置里可切换；
  也可自行添加图片牌组。

## 快速开始（本地开发）

```bash
uv sync
uv run uvicorn webpokerdealer.main:app --reload --host 0.0.0.0 --port 8000
```

> `--reload` 只用于开发：改代码会重启进程，而牌桌状态在内存中，**重启即清空**。
> 实际和家人开玩时去掉它：
> ```bash
> uv run uvicorn webpokerdealer.main:app --host 0.0.0.0 --port 8000
> ```
> 手机 / 平板用 `http://<本机局域网IP>:8000` 访问。

> 主持人控制面需鉴权：创建牌桌后会自动记住主持人身份；换设备打开公牌桌时，
> 需输入创建时生成的 4 位 PIN（可在公牌桌「⚙️ → 主持人」中查看）。玩家入座无需密码。

浏览器打开 `http://localhost:8000`：

1. 点"创建牌桌" → 进入**公牌桌**页面（平板放桌子中间），页面会显示加入二维码。
2. 手机扫描二维码（或手动输入牌桌号）→ 输入昵称入座。
3. 公牌桌点“开始本局”发底牌，各人手机上看到自己的两张牌。
4. 每轮下注结束后，公牌桌点“下一轮”依次翻牌（翻牌 3 张 → 转牌 → 河牌）。
   **发牌到河牌就停**；需要亮牌时再点右侧红色的“摊牌”。
5. 若一局提前结束（都弃牌 / 下注分胜负），直接点“开始下一局”即可，
   不必先把公共牌发完。右上角⚙️可设座位顺序、看牌局历史、重置牌桌。

## 测试

```bash
uv run pytest         # 基线 90 用例全绿（含与参照实现对拍的差分测试 + D3 的泄漏模糊测试）
uv run pytest -m slow  # 穷举 5 张手牌空间（约 15 秒）
```

## 开发提示

- **音效可替换**：默认用 WebAudio 合成；把 `deal.mp3` / `flip.mp3` / `reveal.mp3`
  放进 `src/webpokerdealer/static/audio/` 即可替换（缺哪个就用合成声兜底），
  详见该目录的 `README.md`。
- **牌面可替换**：默认用内置 CSS 牌面；把一套图片牌组放进
  `src/webpokerdealer/static/cards/<牌组>/` 并在 `static/cards/decks.json` 登记，
  即可在「⚙️ → 外观 → 牌面样式」里选择，详见 `static/cards/README.md`。
- **前端无构建步骤**：改 `static/js/*.js` / `static/css/*.css` 后浏览器可能命中缓存，
  需**强制刷新**（`Ctrl+Shift+R`）才看得到新代码。
  （模板已给静态资源加 `?v=<内容哈希>`，正常情况会自动破缓存，重启服务后生效。）
- **WebSocket 错误带 `reason`**（`table_missing` / `bad_token` / `game_error` / ...），
  客户端据此决定是否继续重连（见 `docs/DECISIONS.md` D10）。
- 服务端 `webpokerdealer` logger 会打印带时间戳的 `ws open/close/reject`，
  排查连接问题直接看它。

## Docker 部署（NAS）

```bash
docker compose up -d --build
```

默认映射到宿主机的 `8123` 端口，改用浏览器访问 `http://<NAS-IP>:8123`。
详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 文档

- [docs/ROADMAP.md](docs/ROADMAP.md) —— 进度与下一步
- [docs/DECISIONS.md](docs/DECISIONS.md) —— 已定的技术决策
- [docs/PRIOR-ART.md](docs/PRIOR-ART.md) —— 同类项目调研、可借鉴项与许可证边界
- [docs/DEPLOY.md](docs/DEPLOY.md) —— NAS/Docker 部署
- [AGENTS.md](AGENTS.md) —— 给 AI 助手的项目上下文

## 安全与公平说明

- 洗牌使用 Python `secrets.SystemRandom`（操作系统级随机源）。
- 服务端控制牌堆，底牌只下发给对应玩家，公牌桌在摊牌前也看不到任何人的底牌。
- 本工具只负责发牌与展示，**不记录筹码与下注**（筹码在实体桌上完成），
  也**不提供任何赌博服务**，仅供家庭娱乐使用。

## 许可证

[MIT](LICENSE)。内置牌面 / 音频等素材只收录公有领域或允许再分发的许可；
同类项目调研与第三方代码的许可证边界见 [docs/PRIOR-ART.md](docs/PRIOR-ART.md) 与
`docs/DECISIONS.md` D17。

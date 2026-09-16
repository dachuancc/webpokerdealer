# webpokerdealer

家庭德州扑克**发牌助手**。用浏览器就能跑：一台平板放在桌子中间当"公牌桌"（显示公共牌、控制发牌进度），
每个人用自己的手机打开网页入座，只在自己的手机上看到自己的两张底牌。省去洗牌、发牌的麻烦。

## 特点

- **服务端权威**：牌堆和座位都在服务器上，每台设备只收到它该看到的信息（别人的底牌不会下发到你的手机）。
- **实时同步**：WebSocket 广播，平板点"下一轮"，所有手机立即更新。
- **零构建前端**：Jinja2 模板 + 原生 JS，一个容器同时提供页面 / API / WebSocket。
- **NAS 友好**：单容器 Docker 部署，手机 / 平板通过局域网 IP 访问。

## 快速开始（本地开发）

```bash
uv sync
uv run uvicorn webpokerdealer.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`：

1. 点"创建牌桌" → 进入**公牌桌**页面（平板放桌子中间），页面会显示加入二维码。
2. 手机扫描二维码（或手动输入牌桌号）→ 输入昵称入座。
3. 公牌桌点"开始本局"发底牌，各人手机上看到自己的两张牌。
4. 每轮下注结束后，公牌桌点"下一轮"依次翻牌（翻牌 3 张 → 转牌 → 河牌 → 摊牌）。

## 测试

```bash
uv run pytest
```

## Docker 部署（NAS）

```bash
docker compose up -d --build
```

默认映射到宿主机的 `8123` 端口，改用浏览器访问 `http://<NAS-IP>:8123`。
详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 文档

- [docs/ROADMAP.md](docs/ROADMAP.md) —— 进度与下一步
- [docs/DECISIONS.md](docs/DECISIONS.md) —— 已定的技术决策
- [docs/DEPLOY.md](docs/DEPLOY.md) —— NAS/Docker 部署
- [AGENTS.md](AGENTS.md) —— 给 AI 助手的项目上下文

## 安全与公平说明

- 洗牌使用 Python `secrets.SystemRandom`（操作系统级随机源）。
- 服务端控制牌堆，底牌只下发给对应玩家，公牌桌在摊牌前也看不到任何人的底牌。
- 本工具只负责发牌与展示，**不记录筹码与下注**（筹码在实体桌上完成），
  也**不提供任何赌博服务**，仅供家庭娱乐使用。

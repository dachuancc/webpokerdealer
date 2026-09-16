# DEPLOY — 部署（NAS / 树莓派 / PC）

目标：局域网内一台常开的机器跑一个容器，家里所有手机/平板访问它。宿主可以是
NAS、树莓派或一台 PC；客户端（手机/平板）只浏览器访问，**不需要也不支持在客户端上
跑 Docker**（iPad 更不行，见 §0.3）。

## 0. 部署形态怎么选

| 宿主 | 优点 | 缺点 | 适合 |
|---|---|---|---|
| PC 直接 `uv run uvicorn` | 零配置 | 要开着电脑；IP 可能变 | 临时 / 调试 |
| PC 上 Docker | 隔离、好起停 | 仍要开着 PC | 折中 |
| **NAS Docker** | 常开、稳定 | 需支持 Docker；构建可能慢 | 家里长期 |
| **树莓派 Docker** | 便携、低功耗、便宜 | 外出需供电；换网要重新找地址 | **随身携带** |

要点：牌桌状态在内存（见 `DECISIONS.md` D2），只需“一场牌局期间服务开着”即可。
局域网 + WebSocket 即可，**不需要公网 / 云 / HTTPS**。

## 0.1 镜像：发布多架构，通吃 NAS 与树莓派

Docker 镜像是标准格式，群晖 / 威联通 / TrueNAS / unRAID / 树莓派都能 `docker pull`。
但**架构要对**：多数 NAS 是 `linux/amd64`，树莓派与部分 ARM NAS 是 `linux/arm64`
（64 位系统）或 `linux/arm/v7`（32 位系统）。所以发布**多架构镜像**：

```bash
docker buildx create --use --name wpd
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t <dockerhub-user>/webpokerdealer:latest --push .
# 或用 GHCR（与仓库同源、限额更宽松）：
#   -t ghcr.io/<user>/webpokerdealer:latest --push .
```

- 需先 `docker login`（Docker Hub）或 `docker login ghcr.io`（用 PAT）。
  **凭据只留在本机，切勿提交**（安全红线）。
- NAS / 树莓派上直接 `docker pull` 后 `docker run` 或 compose 即可。
- 以后可加 GitHub Actions 自动构建多架构并推送（按需）。

## 0.2 树莓派便携方案

一台闲置树莓派即可当“随身发牌服务器”：和手机 / 平板在同一局域网就能玩。

- 装 Docker，用本仓库 compose（已是 `restart: unless-stopped`），开启 Docker 开机自启
  → **通电即用**。
- **找地址**：优先 mDNS `http://<主机名>.local:8123`（iOS 支持；**Android 的 `.local`
  解析不总可靠**）。稳妥做法：平板用能解析的地址打开公牌桌，二维码会按当前 Host
  自动生成，玩家扫码即可，无需手输 IP。
- **换网络**：IP 会变，用 `.local` 名字可规避；否则看路由器后台。
- **两个真实坑**：
  1. **访客 Wi‑Fi 的客户端隔离**：有些场地禁止设备互通，手机连不上 Pi。
     解法：让 **Pi 自己开热点**（hostapd / dnsmasq），或带一个迷你旅行路由器；
     热点模式下可设 `WPD_PUBLIC_BASE_URL=http://10.0.0.1:8123` 固定二维码地址。
  2. **供电**：外出用 USB 充电宝给 Pi 供电。
- 下面 NAS 的步骤 1–7 对树莓派同样适用，把“NAS”换成 Pi 即可。

## 0.3 iPad 能跑 Docker 吗？

**不能。** iPadOS 没有 Linux 内核，也限制虚拟机 / 容器所需能力；iPad 在本项目里是
**客户端**（或公牌桌）。宿主用 NAS / 树莓派 / PC。

## 1. 准备

宿主需要装有 Docker（树莓派装 Docker；多数成品 NAS 支持 Docker / Container Manager）。
把仓库放到 NAS 上（`git clone`，或直接用 SCP/共享文件夹拷过去）：

```bash
git clone <repo-url> webpokerdealer
cd webpokerdealer
cp .env.example .env
```

按需编辑 `.env`：

- `WPD_HOST_PORT`：宿主端口，默认 `8123`（改掉可避免与 NAS 上其他服务冲突）
- `WPD_MAX_SEATS`：每桌座位数，默认 `9`
- `WPD_PUBLIC_BASE_URL`：一般留空。**仅当**自动探测的地址不对时再设置
  （例如套了反向代理、或 NAS 有多张网卡），形如 `http://192.168.1.10:8123`

## 2. 构建并启动

```bash
docker compose up -d --build
```

查看状态与日志：

```bash
docker compose ps
docker compose logs -f
```

`ports` 默认把宿主的 `8123` 映到容器的 `8000`。

## 3. 使用

1. 查 NAS 的局域网 IP（例如在路由器后台或 NAS 系统信息里看），假设是 `192.168.1.10`
2. **平板**浏览器打开 `http://192.168.1.10:8123` → 点「创建牌桌」→ 进入公牌桌页面
3. 公牌桌页面有「扫码加入」二维码，手机扫码 → 输昵称入座
   （也可在首页手动输入 4 位牌桌号）
4. 平板放在桌子中间；公牌桌点「开始本局」，各人手机上出现自己的底牌
5. 每轮下注结束后，点「下一轮」依次翻牌；最后一街点「摊牌」

## 4. 关于二维码地址

- 默认用**请求的 Host** 生成加入链接，手机从局域网访问时即为 NAS 的 IP，正常可用
- 若 NAS 前置了反向代理 / 走域名 / HTTPS，请设置 `WPD_PUBLIC_BASE_URL` 为对外可访问的地址
- 手机与 NAS 必须在同一局域网，且 NAS 防火墙放行 `WPD_HOST_PORT`

## 5. 升级

```bash
git pull
docker compose up -d --build
```

## 6. 数据说明

- **无持久化**：牌桌状态在内存中，容器重启 / 重建后所有牌局消失。这是有意设计（见 `docs/DECISIONS.md` D2）
- 无需挂载数据卷

## 7. 停止 / 卸载

```bash
docker compose down          # 停止并删除容器
docker compose down --rmi local   # 连同本地镜像一起删除
```

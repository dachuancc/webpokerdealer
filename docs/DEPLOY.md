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

### 部署前第一件事：确认宿主 CPU 架构

镜像按 CPU 架构分发，**拉错架构会直接起不来**。在宿主机上跑：

```bash
uname -m
# x86_64  → linux/amd64（多数 NAS、PC）
# aarch64 → linux/arm64（树莓派 64 位系统、部分 ARM NAS）
# armv7l  → 32 位系统：本项目**不发布** arm/v7 镜像（原因见 §0.1），
#            树莓派请先刷 64 位系统（Pi 3/4/5、Zero 2 W 都支持）
```

⚠️ **「硬件支持 64 位」≠「系统是 64 位」**：树莓派 4 的 CPU（Cortex-A72 / ARMv8-A）确实
支持 arm64，但若装的是 32 位 Raspberry Pi OS，内核就是 armv7，**arm64 镜像跑不了**
（32 位内核无法执行 64 位容器）。唯一判断依据就是 `uname -m` 的输出。

## 0.1 镜像：发布多架构，通吃 NAS 与树莓派

Docker 镜像是标准格式，群晖 / 威联通 / TrueNAS / unRAID / 树莓派都能 `docker pull`。
但**架构要对**（先做上面的 `uname -m` 自检）：多数 NAS 是 `linux/amd64`，
树莓派与部分 ARM NAS 是 `linux/arm64`。所以发布**多架构镜像**：

```bash
docker buildx create --use --name wpd
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t <dockerhub-user>/webpokerdealer:latest --push .
# 或用 GHCR（与仓库同源、限额更宽松）：
#   -t ghcr.io/<user>/webpokerdealer:latest --push .
```

- **不含 `linux/arm/v7`（32 位 ARM），这是有意的**：`ghcr.io/astral-sh/uv` 不发布 arm/v7
  镜像，且 `uvloop` / `httptools` / `pyyaml` 没有 armv7 预编译 wheel（arm64 有）。
  详见 `DECISIONS.md` D15「修订」。32 位树莓派请先刷 64 位系统。
- **镜像由 CI 构建并推送到 Docker Hub**（打 `v*` tag 触发），用法见 §0.5。
- **在 amd64 机器上交叉构建 arm64**：本机需要 `qemu-user-static` + `binfmt-support`
  （让内核能执行 arm64 二进制）。构建阶段会被模拟、慢一些（实测：单架构 16 秒、
  **双架构 117 秒**）；**镜像跑到 Pi 上是原生执行**，树莓派侧不需要任何模拟层。
  若 buildx 报 `exec format error`，改用 BuildKit 官方推荐的方式重装 handler：
  ```bash
  docker run --privileged --rm tonistiigi/binfmt --install arm64
  ```
- ⚠️ **用 qemu 跑 arm64 镜像时，`HEALTHCHECK` 会误报 `unhealthy`** —— 不是服务有病：
  健康检查要新起一个 `python` 进程，而 qemu 下解释器启动被拉到 ~8.8 秒
  （同一镜像原生只需 **0.12 秒**），超过 Dockerfile 里的 `--timeout=5s`。
  表现：`docker inspect` 里写 `Health check exceeded timeout (5s)`，但 `curl /healthz` 返回 200。
  **真实 arm64 硬件（树莓派）上是原生执行，不会有这个问题**；而且健康检查失败
  **不会**触发重启（`restart: unless-stopped` 只看进程状态），所以即便看到也不影响运行。
  排查真实故障时不要被它误导。

- 需先 `docker login`（Docker Hub）或 `docker login ghcr.io`（用 PAT）。
  **凭据只留在本机，切勿提交**（安全红线）。
- NAS / 树莓派上直接 `docker pull` 后 `docker run` 或 compose 即可。
- 以后可加 GitHub Actions 自动构建多架构并推送（按需）。

## 0.2 树莓派便携方案

一台闲置树莓派即可当“随身发牌服务器”：和手机 / 平板在同一局域网就能玩。

- **必须是 64 位系统**：`uname -m` 显示 `aarch64` 才行（Pi 3/4/5、Zero 2 W 都支持）。
  若显示 `armv7l`，先刷 64 位 Raspberry Pi OS —— 本项目不发布 arm/v7 镜像（见 §0.1）。
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

## 0.4 国内网络：拉镜像会撞的坑（Docker Hub / ghcr.io 的 IPv6）

**症状**：`docker pull python:3.12-slim` 失败，报

```
read tcp [240e:...]:48206->[2600:9000:...]:443: read: connection reset by peer
```

`2600:9000::` 是 Docker Hub 的 CloudFront，`2606:50c0::` 是 GitHub（ghcr.io）。
这两个 registry 的 CDN 走 **IPv6** 时连接会被重置；**不是 DNS、也不是凭据问题**，
重试多少次都一样。

**解法 A（推荐，治本）：给 Docker 配 registry 镜像**（只对 Docker Hub 生效）

```bash
sudo mkdir -p /etc/docker
echo '{"registry-mirrors": ["https://docker.1ms.run"]}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

配完之后 `docker pull python:3.12-slim` 直接可用，不用改镜像名。

**解法 B：ghcr.io 的镜像**（daemon 的 `registry-mirrors` 管不到 ghcr）——先拉镜像源的同名
镜像，再打上官方标签：

```bash
docker pull ghcr.nju.edu.cn/astral-sh/uv:latest
docker tag  ghcr.nju.edu.cn/astral-sh/uv:latest ghcr.io/astral-sh/uv:latest
```

**已实测可用（2026-09）**：

| 用途 | 地址 | 备注 |
|---|---|---|
| Docker Hub | `docker.1ms.run` | **真代理 blob**，可用 |
| ghcr.io | `ghcr.nju.edu.cn` | 南大镜像，可用 |
| ghcr.io | `ghcr.dockerproxy.net` | 备用，可用 |
| ❌ Docker Hub | `docker.m.daocloud.io` | **重定向型**：blob 被指回 CloudFront，照样失败 |

**两个注意**：

- 镜像源看得到你拉取的**公开**镜像（本项目不推私有镜像，可接受）；敏感场景请自建。
- 本仓库的 Dockerfile **故意不写死任何国内镜像源**——保持可移植性，国内网络用上面的办法
  在**宿主机**解决（NAS / 树莓派上同理，一次配好长期有效）。见 `DECISIONS.md` D19。

## 0.5 发布镜像到 Docker Hub（打 tag 自动构建）

镜像由 GitHub Actions 构建：**打一个 `v*` tag 就自动跑测试、构建 amd64+arm64 并推送**。
本地不需要 Docker、不需要凭据。配置在 `.github/workflows/publish.yml`。

**一次性准备**（在网页上操作）：

1. Docker Hub 账号（**邮箱需验证**，否则推不上去）
2. 建一个 access token：Account Settings → Security → New Access Token（**Read & Write**）
3. 在 GitHub 仓库加两个 secret（Settings → Secrets and variables → Actions）：
   - `DOCKERHUB_USERNAME`：你的 Docker Hub 用户名
   - `DOCKERHUB_TOKEN`：上一步的 token

**发布**：

```bash
git tag v0.1.0
git push origin v0.1.0
```

由 tag 推导出的标签：`0.1.0`、`0.1`、`latest`。

**在 NAS / 树莓派上使用**：

```bash
docker pull <你的用户名>/webpokerdealer:latest
```

公开镜像**不需要登录**；NAS 的 Docker 面板里也能直接搜到（这正是选 Docker Hub 的原因）。

> workflow 里的镜像名是 `<DOCKERHUB_USERNAME>/webpokerdealer`（用户名取自 secret）。
> 想换仓库名就改 `images:` 那行。

**为什么推送放在 CI**：本机到 Docker Hub 的 IPv4 通路是好的，但 IPv6 完全不通，
而 Docker 的解析会挑 IPv6；关键是 **registry mirror 只管拉不管推**，所以本机推不可靠。
见 `DECISIONS.md` D20。

**备用方案（拿不到镜像时）**：本机 `save` 成 tar，拷过去 `load`，完全不经过 registry：

```bash
docker save <用户名>/webpokerdealer:latest -o wpd.tar   # 多架构镜像可整体打包
scp wpd.tar <nas>:/tmp/ && ssh <nas> 'docker load -i /tmp/wpd.tar'
```

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

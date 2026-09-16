# DEPLOY — 在 NAS 上用 Docker 部署

目标：一个容器跑在 NAS 上，家里所有手机/平板通过局域网访问。

## 1. 准备

NAS 需要装有 Docker（多数成品 NAS 支持 Docker / Container Manager）。
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

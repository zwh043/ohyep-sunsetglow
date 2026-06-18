# 🚀 部署指南 · Ohyep SunsetGlow

本文档介绍如何把 Ohyep SunsetGlow 部署到服务器或 NAS 上无人值守运行。以**飞牛 NAS（fnOS）** 为例，其他 Linux 设备步骤通用。

> ⚠️ 关键前提：仓库里**没有** `config.yaml` 和 `.env`（含密钥，已被 `.gitignore` 排除）。部署第一件事就是从模板复制并填入你的真实密钥。

## 准备

1. 安装 Docker（飞牛：应用中心搜索 Docker 安装）
2. 开启 SSH 服务（飞牛：设置 → 终端机/SSH，记下端口，默认 22）

## 步骤 1：SSH 登录

在电脑终端：

```bash
ssh 你的用户名@NAS的IP地址
# 例如 ssh fnadmin@192.168.1.100
```

## 步骤 2：下载项目

```bash
cd ~
git clone https://github.com/zwh043/ohyep-sunsetglow.git
cd ohyep-sunsetglow
```

没有 git 时用 zip：

```bash
cd ~
wget https://github.com/zwh043/ohyep-sunsetglow/archive/refs/heads/main.zip
unzip main.zip && mv ohyep-sunsetglow-main ohyep-sunsetglow && cd ohyep-sunsetglow
```

## 步骤 3：创建配置并填密钥（最关键）

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

编辑 `.env` 填入密钥：

```bash
nano .env
```

```
SERVERCHAN_SENDKEY=你的Server酱SendKey
CAIYUN_TOKEN=你的彩云token   # 不用彩云源可留空
```

`Ctrl+O` 回车保存，`Ctrl+X` 退出。

编辑 `config.yaml` 调整监控地点、阈值、反馈链接：

```bash
nano config.yaml
```

> ⚠️ **想用彩云（第三个源）必须手动开启**：`config.example.yaml` 里彩云默认是**关**的（`enabled: false`）。光在 `.env` 填了 `CAIYUN_TOKEN` 不够，还要在 `config.yaml` 里把它打开，否则启动日志只会显示两个源。改成：
>
> ```yaml
>   caiyun:
>     enabled: true     # 改成 true
>     token: ""         # 留空，自动用 .env 里的 CAIYUN_TOKEN
>     threshold: 55
> ```
>
> 没注册彩云、不想用第三个源的话，保持 `enabled: false` 即可，跳过这步。

## 步骤 4：启动

```bash
sudo docker compose up -d --build
```

首次会下载镜像+装依赖，等几分钟。

## 步骤 5：验证

```bash
sudo docker compose logs -f
```

看到 `启用数据源: ['Ohyep算法', 'SunsetBot', '彩云天气']` 即三源全部成功。`Ctrl+C` 退出日志查看（不停容器）。

> 如果日志只显示 `['Ohyep算法', 'SunsetBot']`，说明彩云没启用——回到步骤 3 检查 `config.yaml` 里 `caiyun.enabled` 是不是 `true`、`.env` 里 `CAIYUN_TOKEN` 是否填了，改完 `sudo docker compose restart`。

本地反馈网页：浏览器打开 `http://NAS的IP:8080`

## 日常操作

```bash
sudo docker compose logs -f      # 看日志
sudo docker compose restart      # 重启（改了 config.yaml 后用这个，无需重建）
sudo docker compose down         # 停止
sudo docker compose up -d        # 启动
```

## 要点

- **开机自启 / 重启不丢数据**：`restart: unless-stopped` 已配置，NAS 重启后容器自动拉起；推送记录存在挂载的 `data/` 目录。
- **端口冲突**：8080 被占时，改 `docker-compose.yml` 里 `"8080:8080"` 左边的数字（如 `"8090:8080"`），改用 8090 访问。
- **Server酱额度**：免费版每天 5 条。监控 2 地、晚霞2次+朝霞1次=每地每天最多 3 条，2 地可能触顶。实际阈值（55/0.3/55）下很多天不触发，一般不会天天超额。
- **修改配置**：`config.yaml` 是挂载进容器的，改完 `docker compose restart` 即可生效，不必重新 build。

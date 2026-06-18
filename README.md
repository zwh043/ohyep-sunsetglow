# 🌇 Ohyep SunsetGlow

多数据源的**朝霞 / 晚霞（火烧云）预测推送**工具。持续监控多个城市，任一数据源预测达标就通过微信（Server酱）推送提醒，并提供本地网页记录推送、收集反馈、统计各源准确率。

> 设计理念：**多源并行、宁杀错不放过**。单一预测源（哪怕是专业网站）经常漏报，多个独立来源任一达标即提醒，再用真实反馈持续校准阈值与算法。

## ✨ 特性

- **三数据源并行**，任一触发即推送：
  - **Ohyep算法**：基于 [Open-Meteo](https://open-meteo.com) 免费气象 API（分高度云量、能见度、湿度）+ 火烧云物理评分，无需 Key。
  - **SunsetBot**：抓取专业火烧云预测网站 [sunsetbot.top](https://sunsetbot.top) 的质量指标。
  - **彩云天气**：[彩云](https://platform.caiyunapp.com) 总云量评分，填入免费 token 即可启用。
- **多地点**：配置文件里任意增减城市。
- **朝霞**前一晚提醒（方便早起准备）；**晚霞**推两次——下午「今日预告」+ 日落前「临场提醒」。推送里附当天日出日落时间。
- ⚠️ Server酱免费版每天 **5 条**额度。晚霞2次+朝霞1次=每地每天最多3条，监控 2 个地点可能触顶，按需取舍地点数或调高阈值。
- **准确率反馈闭环**：本地网页点选"未出现/小烧/中烧/大烧"，自动统计各源命中率，便于后续调阈值或算法。
- **Docker 一键部署**，无人值守。

## 🔬 火烧云怎么判断

天空在日出/日落染色，物理上需要三件事同时满足，Ohyep算法据此打 0-100 分：

1. **头顶有"幕布"**：中高层云适中（约 30-60%）时最容易被低角度阳光染红。云太少没东西染，太厚则挡光发灰。
2. **地平线方向不挡光**：太阳那一侧的低层云越少越好。
3. **空气通透**：能见度高、湿度低，颜色才纯。

推送里会附每个源的理由，例如"高云45% 中云30% 低云10%，能见度25km，评分72（很好）"，方便你判断要不要出门拍。

## 🚀 快速开始

### 1. 准备配置

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

编辑 `config.yaml`：填监控地点、调整阈值。每个地点支持三个字段：

| 字段 | 用途 |
|---|---|
| `name` | 显示名（推送里出现） |
| `latitude` / `longitude` | 源①Ohyep算法、源③彩云用的精确坐标。强烈建议手填具体拍摄点——广州这种大城市南北（如靠海的南沙 vs 四面环山的花都）天气差异很大，坐标越准越贴合。不填则按 `name` 自动地理编码到市中心。 |
| `sunsetbot_city` | 源②sunsetbot 查询用名，认识区级名（如 `天河区`、`前海`）。不填则用 `name`。 |

编辑 `.env`：填入 Server酱 SendKey（[申请地址](https://sct.ftqq.com/)），需要彩云源则填 token。

```env
SERVERCHAN_SENDKEY=你的SendKey
CAIYUN_TOKEN=你的彩云token   # 可选，启用源③时填
```

### 2. Docker 运行（推荐）

```bash
docker compose up -d --build
```

- 推送服务后台运行
- 反馈网页：浏览器打开 `http://localhost:8080`

查看日志 / 停止：

```bash
docker compose logs -f
docker compose down
```

### 3. 不用 Docker 直接跑

```bash
pip install -r requirements.txt
python main.py            # 持续运行
python main.py --once     # 只检查一次（调试）
```

## ⚙️ 配置说明

| 配置项 | 说明 |
|---|---|
| `locations` | 监控地点列表。每项 `name` + 可选 `latitude`/`longitude`（源①③精确坐标）+ 可选 `sunsetbot_city`（源②区级查询名） |
| `schedule.sunrise_notify_hour` | 每晚几点检查次日朝霞，默认 22 |
| `schedule.sunset_afternoon_hour` | 晚霞「今日预告」推送钟点，默认 15（下午3点） |
| `schedule.sunset_pre_hours_before` | 晚霞「临场提醒」在日落前几小时推，默认 1 |
| `schedule.check_interval_minutes` | 主循环检查间隔，默认 15 分钟 |
| `sources.own_algo.threshold` | Ohyep算法触发阈值（0-100），默认 55 |
| `sources.sunsetbot.threshold` | sunsetbot 触发阈值（0-1），默认 0.30 |
| `sources.caiyun` | 彩云天气源，填 token 后启用 |
| `web.port` | 反馈网页端口，默认 8080 |

### 调整灵敏度

- 推送太频繁 → 调高对应源的 `threshold`
- 几乎不推 → 调低 `threshold`
- 跑一段时间后，结合网页里的准确率统计来优化各源阈值。

## 📊 准确率反馈闭环

每次推送都会记录到本地 SQLite。出现朝/晚霞后，在网页 `http://localhost:8080` 给那次推送点选实际效果（未出现/小烧/中烧/大烧）。网页顶部会显示各数据源的命中率，帮你判断哪个源更靠谱、阈值是否合适。

## 🧩 扩展

- **加数据源**：继承 `app/sources/base.py` 的 `PredictionSource`，实现 `predict()`，在 `app/sources/__init__.py` 注册即可，主循环无需改动。
- **加推送渠道**：`app/pusher.py` 已预留 WxPusher，配置里开启并填 token。

## 📁 项目结构

```
ohyep-sunsetbot/
├── main.py                  # 主循环调度
├── config.example.yaml      # 配置模板（复制为 config.yaml）
├── app/
│   ├── scoring.py           # 火烧云评分算法
│   ├── storage.py           # SQLite 记录 + 反馈 + 准确率统计
│   ├── pusher.py            # Server酱 / WxPusher 推送
│   ├── sources/             # 三个数据源
│   │   ├── base.py          # 统一接口与数据结构
│   │   ├── own_algo.py      # 源①Ohyep算法
│   │   ├── sunsetbot.py     # 源②sunsetbot.top
│   │   └── caiyun.py        # 源③彩云天气
│   └── web/                 # 反馈网页（Flask）
├── Dockerfile
└── docker-compose.yml
```

## 🙏 致谢

- [fengfengzhidao/sunsetbot](https://github.com/fengfengzhidao/sunsetbot) — 火烧云预测机器人开源项目，本项目 sunsetbot 数据源的接口参考来源，特此致谢。
- [Open-Meteo](https://open-meteo.com) — 免费、开源、无需 Key 的气象数据 API。
- [sunsetbot.top](https://sunsetbot.top) — 专业的火烧云预测服务。
- [彩云天气](https://caiyunapp.com) — 提供分钟级降水与逐小时气象数据 API。
- [Server酱·Turbo](https://sct.ftqq.com/) — 微信消息推送服务。

## ⚠️ 说明

- 天气预报本身有不确定性，预测是概率参考而非保证，越临近越准。
- 本项目抓取 sunsetbot.top 仅供个人学习使用，请遵守对方服务条款，控制请求频率。
- 切勿将含密钥的 `config.yaml` / `.env` 提交到公开仓库（已在 `.gitignore` 中排除）。

## 📄 License

[MIT](LICENSE)

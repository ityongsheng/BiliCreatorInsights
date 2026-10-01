# BiliCreatorInsights

B 站创作者分析助手：抓取热门视频和评论，清洗后做情绪分析、关键词、观众画像和痛点归因，并给出可执行的创作建议。

## 能做什么

- 拉取热门视频（不足时补全站排行），按分区名称或 tid 过滤
- 增量抓取一层评论和回复（已存的 `rpid` 会跳过）
- 清洗：广告、纯表情/符号、过短文本、同一用户的重复发言、SimHash 近重复
- 词典 + 否定/程度窗口 + 少量语义增强，输出 positive / neutral / negative，分数 0–1（0.5 为中性）
- TF-IDF 与 TextRank 抽 top 20 关键词（jieba 词性只保留名词、动词、形容词）及共现
- 用户画像：情绪类型（支持型 / 质疑型 / 讨厌型 / 讨论型 / 建议型）、参与度、正负比、关键词、风格，并做分群
- 把负面评论归到内容、节奏、互动、质量、价格等主题，按优先度排序，附最多 3 条原句
- 导出 JSON、Markdown、PDF，并提供一个中文单页看板

## 怎么运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --host 0.0.0.0 --port 8787
```

浏览器打开 `http://127.0.0.1:8787`。

数据库默认是 `data/insights.db`（已写入 `.gitignore`，重启后数据还在）。可以用环境变量 `BILI_DB_PATH` 改位置。

首次打开看板会读库。库是空的时，`GET /api/videos/hot` 会请求 B 站；也可以手动 `GET /api/videos/hot?refresh=true`。请求带浏览器 User-Agent，两次请求之间有短暂间隔，出错就停止。

评论先请求 `/x/v2/reply`。这个环境里它经常返回空列表而不是报错，客户端会接着请求公开的 WBI 接口 `/x/v2/reply/wbi/main`（热门、时间序各一页）和 `/x/v2/reply/reply` 里的回复。签名用的是 `/x/web-interface/nav` 下发的图片密钥，设备号来自 `/x/frontend/finger/spi`，不是登录态。`/x/web-interface/view` 若返回 412，视频统计仍用热门列表里已经拿到的数字。单条线程目前往往只能取回第一页回复，所以实际入库条数以接口返回为准，不会补假评论。

## 演示数据

仓库自带 `app/demo_data.py`。只有在 B 站热门接口失败或返回空、并且本地还没有任何视频时，才会写入数据库。演示视频标题都以 **【演示】** 开头，`is_demo=true`，接口里的 `source` 为 `demo`。这些播放量和评论是编出来的样本，不是实时统计。一旦成功抓到真实热门列表，演示行会被删掉，避免混在一起。

## 热度分和趋势分

热度分把播放、点赞、投币、收藏、评论、分享压到对数上再加权，避免播放量把互动项淹没，数值大约在 0 到 8：

```text
heat = 0.40 * log10(1+view) + 0.22 * log10(1+like) + 0.12 * log10(1+coin)
     + 0.12 * log10(1+favorite) + 0.08 * log10(1+reply) + 0.06 * log10(1+share)
```

趋势分看每小时播放增量，再用点赞率放大“涨得快而且被认可”的视频：

```text
若有上一次快照 (view_prev, t_prev)：
  hours = max((now - t_prev) / 3600, 0.05)
  velocity = max(view - view_prev, 0) / hours
否则用发布后的平均速度近似：
  hours = max((now - pubdate) / 3600, 0.5)
  velocity = view / hours
trend = log10(1 + velocity) * (1 + 5 * like / max(view, 1))
```

实现和注释在 `app/scoring.py`。每次抓取会写一条 `stat_snapshots`，下次就能用真实增量，而不是平均速度。

## 情感样本

`app/sentiment_samples.py` 里有 41 条人工标注的清晰句子（含否定）。`tests/test_sentiment.py` 会当场计算准确率，阈值是 75%。最近一次在这 41 条上的测量结果是 **41/41**。这不是第三方评测集，也不能当成任意 B 站评论的准确率。

## 分区

`partition` 接受分区名（动画、游戏、生活、知识、美食、音乐、影视、科技、鬼畜、时尚、娱乐等），`rid` 接受 tid。传入父分区 id（例如游戏 `4`、生活 `160`、动画 `1`）时会带上代码里列出的常见子分区。映射在 `app/partitions.py`。

## API

成功时 HTTP 200，正文 `{"ok": true, "data": ...}`。失败时使用对应的 HTTP 状态码，正文 `{"ok": false, "error": "..."}`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 中文看板 |
| GET | `/api/videos/hot` | 热门列表。查询参数 `partition`、`rid`、`refresh`、`limit` |
| GET | `/api/videos/{bvid}` | 视频详情 |
| GET | `/api/videos/{bvid}/comments` | 评论。`include_filtered`、`since`、`until`、`limit` |
| GET | `/api/videos/{bvid}/analysis` | 完整分析 |
| GET | `/api/videos/{bvid}/sentiment` | 情绪分布和按日趋势 |
| GET | `/api/videos/{bvid}/keywords` | 关键词、共现、短语 |
| GET | `/api/videos/{bvid}/profile` | 用户画像和分群 |
| GET | `/api/videos/{bvid}/pain-points` | 痛点 |
| GET | `/api/videos/{bvid}/report.md` | 下载 Markdown |
| GET | `/api/videos/{bvid}/report.pdf` | 下载 PDF |
| GET | `/api/videos/{bvid}/report.json` | 下载 JSON |
| POST | `/api/tasks/analyze` | 正文 `{"bvid": "BVxxxx"}`，后台线程分析 |
| GET | `/api/tasks/{task_id}` | 任务状态：pending / running / done / failed |

PDF 使用随仓库附带的文泉驿微米黑（Apache-2.0，见 `app/fonts/NOTICE.txt`），这样没有系统中文字体也能导出。

## 测试

`pytest` 不访问 B 站。评论清洗、标注样本情感、关键词、痛点画像、增量 `rpid` 和演示数据上的 API 都在本地跑。

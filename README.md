# AI 产业链股票池

一个面向研究工作的开源股票池信息页，覆盖美股、A 股映射、AI 产业链位置、关系图谱、主动发现和政策压力指数。

[![Live Demo](https://img.shields.io/badge/demo-stocks.mastersgo.cc-ff6b35)](https://stocks.mastersgo.cc)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fyaoleifly%2Fai-stock-pool&project-name=ai-stock-pool&repository-name=ai-stock-pool)
[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/yaoleifly/ai-stock-pool)

> 这是研究工具，不是自动交易系统。股票池映射、候选评分和政策压力均不构成投资建议。

## 功能

- 美股与 A 股统一股票池，支持市场、产业链位置和主题筛选。
- 产业关系图谱，支持缩放、全屏、弱关系隐藏和主题聚焦。
- 主动发现：聚合官方信号、新闻、arXiv 论文、当前股票池和行情位置。
- 政策压力指数：综合净支持率、美债、MOVE、标普 500、VIX 与 CPI Nowcast。
- Vercel Python Functions 实时行情与政策压力接口。
- Cloudflare Workers 静态资源与同路径 API 适配。
- 不依赖前端框架，核心页面可直接阅读和修改。

## 一键部署

### Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fyaoleifly%2Fai-stock-pool&project-name=ai-stock-pool&repository-name=ai-stock-pool)

Vercel 版本使用仓库内的 Python Functions：

- `/api/health`：股票池与市场计数。
- `/api/quotes`：Yahoo Finance 行情聚合，60 秒缓存。
- `/api/policy`：政策压力六项指标，300 秒缓存。

无需配置 API Key。部署完成后，Vercel 会自动连接你克隆出的 Git 仓库，后续提交会触发新部署。

### Cloudflare Workers

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/yaoleifly/ai-stock-pool)

Cloudflare 会构建 `dist/` 静态资源并部署一个 Worker：

- `/api/health` 由 Worker 根据当前 `stock-pool.csv` 本地计算。
- `/api/quotes` 与 `/api/policy` 默认代理公开演示接口 `https://stocks.mastersgo.cc`。
- 上游不可用时，政策页会降级到仓库内快照；页面和研究数据仍可浏览。

如需使用自己的兼容 API，把 Wrangler 变量 `UPSTREAM_API_ORIGIN` 改为你的服务地址即可。这个变量不是密钥。

## 本地运行

需要 Python 3.11+：

```bash
python3 -m pip install -r requirements.txt
python3 server.py --port 8765
```

打开 `http://127.0.0.1:8765`。

Cloudflare 版本需要 Node.js 20+：

```bash
npm install
npm run check
npx wrangler dev
```

## 更新数据

刷新主动发现数据：

```bash
python3 discovery_engine.py \
  --fresh \
  --days 7 \
  --max-arxiv-results 8 \
  --max-feed-items 15 \
  --max-extra-quotes 40 \
  --arxiv-delay 3
```

脚本会生成：

- `discovery-signals.csv`
- `arxiv-papers.csv`
- `discovery-candidates.csv`
- `reports/discovery-YYYY-MM-DD.md`

运行后先执行 `npm run validate:data`。如果信号和候选意外变成空表，不要发布；这通常意味着网络抓取失败，而不是市场没有信号。

重新合并自有美股和 A 股源表：

```bash
python3 sync_pool.py \
  --us-source /path/to/us-stock-pool.csv \
  --a-share-source /path/to/a-share-mapping.csv
```

省略参数时，默认读取项目上一级目录中的 `美股股票池.csv` 与 `A股映射股票池.csv`。你也可以直接维护部署用的 `stock-pool.csv`。

## 数据文件约定

| 文件 | 用途 |
|---|---|
| `stock-pool.csv` | 正式股票池部署快照 |
| `discovery-signals.csv` | 官方与新闻信号 |
| `arxiv-papers.csv` | arXiv 论文信号 |
| `discovery-candidates.csv` | 候选评分与处理状态 |
| `discovery-history.csv` | 每日发现趋势 |
| `tpi-latest.json` | 政策压力降级快照 |

前端只读取这些公开快照和同域 `/api/*`，因此不需要数据库。

## 项目结构

```text
index.html / app.js / styles.css  页面与交互
api/                             Vercel Python Functions
cloudflare/                      Cloudflare Worker 与测试
scripts/                         静态构建和数据完整性检查
reports/                         主动发现日报
policy_engine.py                 政策压力计算
discovery_engine.py              主动发现引擎
server.py                        本地服务与行情接口
vercel.json                      Vercel 配置
wrangler.jsonc                   Cloudflare Workers 配置
```

## 安全与隐私

- 仓库不需要 API Key、数据库密码或交易账户凭证。
- `.env*`、`.dev.vars`、`.vercel/`、`.wrangler/` 不会提交。
- 不要把券商账户、持仓明细、内部研究材料或付费数据源内容提交到公开仓库。
- 漏洞请通过 GitHub Security Advisory 私下报告，参见 [SECURITY.md](SECURITY.md)。

## 许可证和数据边界

代码采用 [MIT License](LICENSE)。股票代码、行情、新闻、论文和政策数据仍受各原始数据提供方条款约束；仓库中的生成快照仅用于演示与研究，详见 [NOTICE](NOTICE)。

欢迎提交 Issue 和 Pull Request，贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## English

AI Stock Pool is a framework-free research dashboard for US equities, A-share mappings, industry-chain graphs, active discovery, and policy-pressure signals. It ships with Vercel Python Functions and a Cloudflare Workers adapter. Use the deploy buttons above to create your own copy.

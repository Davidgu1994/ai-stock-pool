# Contributing

**简体中文** · [English](CONTRIBUTING.en.md)

感谢你改进 AI 产业链股票池。

## 提交前

1. 不要提交密钥、账户信息、持仓截图、付费研究全文或受限数据。
2. 股票映射需要标注证据层级，主题相关不能写成已确认供应关系。
3. 数据抓取失败时不得用空 CSV 覆盖有效快照。
4. 新增功能需要同时考虑 Vercel 和 Cloudflare 的行为差异。

## 本地检查

```bash
npm install
npm run check
node --check app.js
python3 -m py_compile server.py policy_engine.py discovery_engine.py
```

如果系统 Python 无法写入用户缓存，可设置 `PYTHONPYCACHEPREFIX` 到临时目录后重试。

## Pull Request

- 说明改动解决的问题和用户影响。
- 列出验证方式与已知限制。
- 数据更新请注明生成日期、信号数、论文数、候选数和抓取警告。
- 页面改动请避免把研究映射表述为确定的投资建议。

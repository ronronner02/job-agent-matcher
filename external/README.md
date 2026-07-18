# external/ — 第三方采集引擎

这个目录用于放置**外部采集引擎**，不属于本项目主代码，也不提交到本仓库
（`.gitignore` 只保留本说明文件）。

本项目 `job-agent-matcher` 是主项目，负责岗位数据的归一化、结构化、技能分析、
简历匹配和报告生成。真实的 Chrome CDP 岗位采集由外部开源项目
[`boss-zhipin-scraper`](https://github.com/) 完成，本项目通过
`app/integrations/boss_zhipin` 适配器调用它，二者边界清晰、互不耦合。

## 如何准备

1. 获取 `boss-zhipin-scraper` 源码，放到本目录下：

   ```text
   external/boss-zhipin-scraper/
     └── scripts/boss_cdp_raw.py
   ```

2. 让本项目知道它的位置，二选一：

   - 在 `.env` 中设置：

     ```dotenv
     BOSS_SCRAPER_ROOT=external/boss-zhipin-scraper
     ```

   - 或运行脚本时显式传入：

     ```bash
     python scripts/run_full_job_agent.py --scraper-root external/boss-zhipin-scraper ...
     ```

适配器会自动识别 `external/boss-zhipin-scraper` 或多套一层目录
（例如解压得到的 `boss-zhipin-scraper-master/boss-zhipin-scraper-master`）。

## 合规提醒

外部采集引擎必须遵守本项目的合规边界：低频采集、专用 Chrome Profile、
不自动投递、不自动沟通、不复用主浏览器登录态。

# Design Decision: Project Boundary

## 决策

项目以 `boss-zhipin-scraper` 的 CDP 采集能力作为数据入口，不以 `browser-use` 作为主框架。`browser-use` 只作为 CDP 连接和 Profile 管理的设计参考。

## 背景

系统定位是“招聘数据 Agent”，核心能力包括岗位采集、JD 结构化、技能统计、简历匹配和报告生成。网页点击、输入和滚动模拟不属于核心业务链路，也会降低系统的稳定性和可复现性。

## 取舍

选择 CDP 采集的好处：

- 更符合岗位数据采集入口。
- 可以复用专用 Chrome 登录态。
- 输出 JSON / CSV 后，后续数据处理链路更清晰。
- 系统能力可以集中在标准化、结构化、匹配和评估。

放弃 browser-use 主线的原因：

- browser-use 更适合通用浏览器动作型 Agent。
- 对本项目来说，网页动作规划不是核心能力。
- 引入完整 browser-use 会增加依赖和解释成本。

## 影响

后续模块按以下顺序实现：

1. Collector Adapter
2. JobNormalizer
3. JDStructurer
4. SkillAnalyzer
5. ResumeParser
6. ResumeMatcher
7. ReportGenerator
8. Evaluation

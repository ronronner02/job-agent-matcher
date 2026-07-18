# Design Decision: CDP Profile and Collection Safety

## 决策

本项目真实采集必须先通过 `CollectionSafetyPolicy` 检查。默认只允许低频、手动确认、专用 Chrome Profile 的岗位采集请求；拒绝主浏览器 Profile、复制主浏览器登录态、自动投递和自动发送消息。

## 为什么需要专用 Chrome Profile

CDP 会连接一个真实 Chrome 上下文。如果直接复用主浏览器 Profile，采集脚本理论上可能接触到主浏览器里的账号、Cookie、历史记录和扩展状态。专用 Profile 把风险缩小到 BOSS 求职场景内：

- 只保存 BOSS 专用登录态。
- 不影响主 Chrome、GitHub、邮箱、网银等账号。
- 便于清理或重建。
- 便于解释为一个受控的采集环境。

原 `boss-zhipin-scraper` 默认 profile 是：

```text
~/.boss-zhipin-scraper/chrome-profile
```

本项目沿用这个默认目录，但在自己的系统里增加采集请求检查，避免调用真实采集前传入危险参数。

## 为什么不默认复制登录态

`--copy-login-state` 会复制主 Chrome 的 `Local State` 和 Cookie 相关文件到专用 Profile。虽然原工具把它设计成显式参数，但它仍然是高风险操作：它把“主浏览器敏感状态”和“采集环境”连接起来。

本项目默认禁止复制登录态，推荐做法是在专用 Chrome 里手动登录 BOSS，避免把个人浏览器隐私暴露给采集脚本。

## 频率限制

原工具单次最大页数是 `10`，默认页数是 `3`。本项目面向个人低频求职分析，因此采用更保守的默认安全策略：

```text
BOSS_MAX_PAGES_PER_RUN=3
BOSS_MIN_SECONDS_BETWEEN_RUNS=600
```

`BOSS_MIN_SECONDS_BETWEEN_RUNS` 目前作为策略配置保留，后续接入 `agent_runs` 后用于防止短时间重复采集。

## 代码落点

- `app/schemas/collect.py`：定义采集请求字段。
- `app/services/collection_safety.py`：检查请求是否越界。
- `scripts/check_collection_safety.py`：命令行安全检查工具。
- `tests/test_collection_safety.py`：验证安全策略会拒绝危险请求。

## 被拒绝的请求

- `pages` 超过低频限制。
- `copy_login_state=True`。
- `use_main_browser_profile=True`。
- `profile_dir` 看起来像主 Chrome / Edge / Chromium Profile。
- `auto_apply=True`。
- `auto_message=True`。

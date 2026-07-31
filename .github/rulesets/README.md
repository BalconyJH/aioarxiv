# 仓库 Ruleset

本目录保存可审计的 GitHub Ruleset 导入文件。GitHub 不会仅因这些文件位于
`.github/rulesets/` 就自动应用它们；需要在
`Settings > Rules > Rulesets > Import a ruleset` 中手动导入。

- `protect-main.json` 保护默认分支 `main`：禁止删除与非快进推送，要求线性历史，
  仅允许 squash 合并的 Pull Request 且至少需要一次批准，并要求
  `Required Checks`（`.github/workflows/ci.yml`）、
  `Coverage Matrix`（`.github/workflows/coverage.yml`）和
  `Prek`（`.github/workflows/prek.yml`）状态检查通过。
- `protect-release-tags.json` 禁止删除或非快进更新 `refs/tags/v*`，
  确保已发布版本的标签保持不可变。

重命名工作流的汇总 job 时，必须同步更新 `protect-main.json` 中对应的
`required_status_checks` context。先等待远端至少产生一次新的检查 context，
再更新已经导入的 Ruleset。

# 仓库治理

workflow 和 Ruleset JSON 只能描述期望契约，不能自动修改 GitHub、PyPI 或 TestPyPI
的远端设置。管理员必须显式配置并定期审计本页列出的保护。

## 分支与标签

仓库提供两份可导入配置：

- `.github/rulesets/protect-main.json`
- `.github/rulesets/protect-release-tags.json`

在 `Settings > Rules > Rulesets > Import a ruleset` 中依次导入并检查目标后启用。

`Protect main` 的基线为：

- 禁止删除与非快进更新默认分支；
- 要求线性历史；
- 只允许 squash merge；
- 至少一次批准，推送新提交后撤销旧批准；
- 要求 review thread 全部解决；
- 要求分支为最新；
- 要求 `Required Checks`、`Coverage Matrix`、`Prek` 成功；
- 不配置日常 bypass。

`Protect release tags` 匹配 `refs/tags/v*`，禁止删除和非快进更新，但允许 Auto Tag
创建新标签。修改 workflow 汇总 job 名称时，先让远端至少观察到一次新的 check
context，再同步更新并重新导入 Ruleset，避免门禁永久等待不存在的名称。

## Deployment environment 与 Trusted Publisher

Ruleset 保护 Git 引用，deployment environment 保护不可逆的包发布权限，两者不能
互相替代。

| GitHub environment | Workflow | 远端 Trusted Publisher |
| --- | --- | --- |
| `release` | `.github/workflows/publish.yml` | PyPI 项目 `aioarxiv` |
| `testpypi` | `.github/workflows/publish-test.yml` | TestPyPI 项目 `aioarxiv` |

两处 Trusted Publisher 均应配置：

- owner：`BalconyJH`
- repository：`aioarxiv`
- workflow filename：分别为 `publish.yml`、`publish-test.yml`
- environment name：分别为 `release`、`testpypi`

不要保存长期 PyPI API token。workflow 只在实际上传的 job 中请求
`id-token: write`，由 environment 与 Trusted Publisher 共同限定 OIDC 身份。
`release` 应只接受版本标签的正常发布和默认分支上的人工恢复；feature branch
不能取得正式发布权限。

## GitHub Pages

在 `Settings > Pages` 中选择从 `gh-pages` 分支根目录部署。该分支完全由 workflow
维护，不属于源码，不应接受人工编辑或 force push。

Pages 同时包含：

- `dev/`：`main` 文档变更的滚动版本；
- `<version>/` 与 `latest/`：正式发布文档；
- `pr-preview/pr-<number>/`：Pull Request 临时预览。

这些路径共用同一个 origin，并不提供浏览器安全隔离。不要在 Pages origin 保存
secret、token 或可信浏览器状态；详细风险见[持续集成](ci.md#docs-preview)。

## Codecov

`CODECOV_TOKEN` 是可选的 repository secret。未配置时 workflow 会尝试无 token
上传；上传失败不会破坏 pytest 与覆盖率门禁。若项目设置为私有或 Codecov 要求
认证，再创建该 secret，不要把 token 写入 workflow 或仓库文件。

## 初次启用顺序

1. 合入 workflow，让 GitHub 至少观察到一次 `Required Checks`、
   `Coverage Matrix` 和 `Prek`。
2. 配置 `release`、`testpypi` environment。
3. 在 PyPI 与 TestPyPI 创建对应 Trusted Publisher。
4. 配置 Pages 从 `gh-pages` 分支根目录部署。
5. 导入并启用 `Protect main`。
6. 导入并启用 `Protect release tags`。
7. 使用非版本变更 Pull Request 验证合并门禁与文档预览。
8. 手动运行 TestPyPI workflow 验证 OIDC、构建和安装。
9. 最后通过正常版本 Pull Request 验证完整发布链。

不得使用真实 `v*` 标签测试删除或移动保护。标签不可变规则应通过 Ruleset 配置审计
和一次正常自动发布确认。

## 审计清单

每次修改 Actions、job 名称、environment 或发布权限后检查：

- `main` Ruleset 是否仍绑定三个实际存在的汇总 context；
- `v*` 标签 Ruleset 是否为 Active 且没有日常 bypass；
- PyPI/TestPyPI Trusted Publisher 的仓库、workflow、environment 是否精确匹配；
- Pages source 是否仍为 `gh-pages` 根目录；
- workflow 的第三方 Action 是否固定到完整 SHA；
- 顶层权限是否保持空或只读，写权限是否只存在于最小 job；
- feature/fork Pull Request 是否无法取得写权限或发布 OIDC；
- `make check`、`make build-artifacts`、`make docs-build` 与 workflow 静态检查是否通过。

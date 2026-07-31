# 持续集成

本页描述 `.github/workflows/` 中各条 GitHub Actions 的职责、合并门禁和信任边界。
发布状态机见[发布与恢复](release.md)，GitHub 远端设置见[仓库治理](governance.md)。

## 工作流总览

| 工作流 | 文件 | 触发条件 | 职责 |
| --- | --- | --- | --- |
| CI | `ci.yml` | `main` push、Pull Request、手动 | 格式、lint、类型、打包与 wheel 安装验证 |
| Coverage | `coverage.yml` | `main` push、Pull Request、手动 | Python 3.10–3.14 测试与覆盖率门槛 |
| Prek | `prek.yml` | `main` push、Pull Request、手动 | 仓库 hooks 与 GitHub Actions 静态检查 |
| CodeQL | `codeql.yml` | `main` push、Pull Request、每周 | Python 安全扫描 |
| Docs | `docs.yml` | 文档输入变更的 `main` push、手动 | 严格构建并更新 `dev` 文档 |
| Docs PR Preview Build | `docs-pr-preview.yml` | Pull Request | 在只读上下文构建预览 artifact |
| Docs PR Preview Deploy | `docs-pr-preview-deploy.yml` | 预览构建完成 | 验证并部署静态预览 |
| Docs PR Preview Cleanup | `docs-pr-preview-cleanup.yml` | Pull Request 关闭 | 删除对应预览 |
| Auto Tag on Version Change | `auto-tag.yml` | required workflow 完成、手动恢复 | 汇合精确 SHA 门禁并创建版本标签 |
| Publish | `publish.yml` | Auto Tag dispatch、手动恢复 | 发布 PyPI、GitHub Release 与版本文档 |
| Publish (TestPyPI) | `publish-test.yml` | 仅手动 | 发布唯一开发版本用于人工验收 |

所有第三方 Action 均固定到完整 commit SHA；顶层默认权限为空或只读，写权限只授予
实际需要产生远端状态的 job。Dependabot 每周分别更新 GitHub Actions 与 uv 依赖。

## 合并门禁

可导入的 `Protect main` Ruleset 绑定三个稳定的汇总 check：

- `Required Checks`：汇总 CI 内部全部 job；
- `Coverage Matrix`：要求完整 Python 版本矩阵成功；
- `Prek`：要求仓库 hooks 和 actionlint 成功。

汇总 job 使用 `if: always()`，因此内部 job 失败、取消或跳过都不会被误判为成功。
Ruleset 无需绑定会随 Python 版本或内部任务扩展而变化的矩阵名称。

### CI 分层

| job | 验证内容 |
| --- | --- |
| `Ruff` | `ruff format --check` 与 `ruff check` |
| `Ty` | `ty check` |
| `Basedpyright` | 源码类型检查和 `aioarxiv` 公开类型完备性 |
| `Package Build` | wheel、sdist 与包元数据 |
| `Wheel Smoke` | Python 3.10、3.11、3.13、3.14 隔离安装与导入 |
| `Required Checks` | 汇总以上所有结果 |

Python 3.12 的完整 wheel 与 sdist 隔离安装由构建验证覆盖；其余受支持版本通过 wheel
smoke 验证运行时依赖和导入边界。对应的本地聚合命令是：

```bash
make check
make build-artifacts
```

## 覆盖率

Coverage 对 Python 3.10–3.14 分别运行测试，单个矩阵项必须达到 75% 项目覆盖率。
测试日志与 XML 报告无论成功或失败都会作为 artifact 保留 14 天。

Codecov 上传不属于正确性门禁：仓库可以配置 `CODECOV_TOKEN`，也可以尝试无 token
上传；外部服务故障不会覆盖 pytest 与覆盖率门槛的真实结果。

## 文档构建与 PR 预览 { #docs-preview }

文档相关 Pull Request 采用构建与部署分离的两段式信任模型：

1. `Docs PR Preview Build` 在 PR 的只读 token 上下文执行不受信任代码，只上传
   生成后的 `site/` artifact。
2. `Docs PR Preview Deploy` 由默认分支中的 `workflow_run` 定义运行。它重新解析当前
   Pull Request，要求上游 run、PR、head SHA 一致，并拒绝过期或歧义关联。
3. 部署前只接受普通文件和目录，拒绝符号链接与其他文件类型，并限制 artifact
   为最多 10000 个文件、100 MiB。
4. 受信任 job 只把验证后的静态内容写入 `gh-pages/pr-preview/pr-<number>/`，
   不 checkout PR 分支，也不执行 artifact 中的程序。
5. Pull Request 关闭后，cleanup workflow 删除固定编号的预览路径并更新评论。

!!! warning "Pages origin 不是安全隔离边界"

    PR 预览与正式文档共用 `https://balconyjh.github.io` origin。公开 fork 可以控制
    预览 HTML/JavaScript，因此该 origin 不得保存 secret、token 或被正式页面信任的
    浏览器状态。评审预览时建议使用不含敏感登录状态的浏览器 profile。

`Docs` 对文档输入使用路径过滤，只在需要时严格构建并把滚动版本部署为 `dev`。
由于它不会为每个 `main` SHA 产生 run，Auto Tag 的精确 SHA 门禁只汇合始终运行的
CI、Coverage 和 Prek；发布 workflow 会从已验证标签再次严格构建版本文档。

## 并发与精确 SHA

Pull Request 更新会取消同一 PR 的过期 CI、Coverage、Prek 和预览构建。`main`
push 则以 commit SHA 作为并发键，不会因后续提交到达而取消，因为 Auto Tag 必须
汇合同一 source SHA 的完整结果。

Auto Tag 的多个 `workflow_run` 事件按 source SHA 串行化。每次事件都会通过 GitHub
API 查询同一 SHA 的三条 required workflow；只有全部处于
`completed/success` 才进入版本检测。后续发布不依赖“当前最新 run”或移动中的
`main`，而只依赖已经确定的 commit 与标签。

## 诊断

手动触发 CI、Coverage 或 Docs 时可启用 `debug_enabled`，输出 runner 或依赖快照。
失败日志、覆盖率报告、构建日志及分发包会以短期 artifact 保存。

本地检查 workflow：

```bash
uv tool run prek run check-github-workflows --all-files
uv tool run prek run zizmor --all-files
uv tool run prek run actionlint --all-files --hook-stage=manual
```

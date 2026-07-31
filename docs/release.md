# 发布与恢复

aioarxiv 使用版本提交、不可变标签和受限权限 job 组成发布状态机。正常发布不监听
任意 tag push；只有精确 SHA 门禁通过后的 Auto Tag dispatch，或维护者显式执行的
恢复操作，才能启动 `Publish`。

## 发布不变量

正式发布必须同时满足：

- source commit 位于 `main` 历史中；
- `project.version` 是规范的 PEP 440 版本且不包含 local segment；
- 标签严格等于 `v<project.version>`，并指向 source commit；
- `uv.lock` 与项目元数据一致；
- PyPI、GitHub Release 使用同一批已经验证的 wheel 与 sdist；
- `refs/tags/v*` 不允许删除或移动。

## 正常发布

1. 创建只包含发布准备与版本提升的 Pull Request，并更新
   `pyproject.toml` 与 `uv.lock`。
2. 合入 `main` 后，CI、Coverage 和 Prek 为该 source SHA 完整运行。
3. 任一 required workflow 完成都会唤醒 Auto Tag。它通过 API 汇合同一 SHA
   的三条结果，而不是信任触发自己的单条 run。
4. Auto Tag 验证 source 仍位于 `main`，比较第一父提交与当前
   `project.version`；正常路径要求版本严格递增。
5. 在创建标签前构建 wheel 与 sdist，执行 Twine、archive 内容及隔离安装验证。
6. 创建带注释的 `v<version>` 标签并显式 dispatch `Publish`。
7. Publish 从标签重新 checkout 和构建，不复用 Auto Tag runner 中的临时文件。
8. `publish-pypi` 仅获得 `id-token: write`，通过 `release` environment 的
   Trusted Publisher 上传 PyPI。
9. `verify-pypi` 从 PyPI JSON 读取文件名与 SHA-256，要求远端文件集合和本次
   artifact 完全一致。
10. 远端分发包验证完成后才创建 GitHub Release，并附加同一批 artifact。
11. 最后从已验证标签严格构建版本文档，部署到 `/<version>/`；若该版本不早于
    当前最新文档，同时更新 `latest`。

构建 job 不持有 PyPI OIDC 或仓库写权限，PyPI job 不持有 GitHub Release 权限，
GitHub Release job 也不持有 PyPI 凭据。artifact 是这些权限边界之间唯一的分发包
传递方式。

## TestPyPI 预演

`Publish (TestPyPI)` 仅供维护者手动触发，不属于 Pull Request 门禁。它在当前项目
版本后添加基于 UTC 时间与 workflow run 的唯一 `.dev` 后缀，构建并完成正式发布
同等级别的分发包验证，再通过 `testpypi` environment 的 Trusted Publisher 上传。

TestPyPI 用于人工检查安装、依赖和元数据，不能替代正式发布的 source、tag、版本
与 PyPI 哈希不变量。

## 恢复路径

| 失败位置 | 恢复方式 |
| --- | --- |
| required workflow 失败 | 修复后通过新的 Pull Request；不要手工打标签 |
| Auto Tag 的分发包 preflight 失败，尚未创建标签 | 修复基础设施并等待当前 `main` SHA 的三条门禁成功；从默认分支手动运行 Auto Tag，输入该完整 `source_sha` |
| 标签已经创建，但 Publish 未启动或失败 | 从默认分支或同名标签手动运行 Publish，输入现有 `release_tag` |
| PyPI 已上传，GitHub Release 或文档失败 | 对同一标签重跑 Publish；`skip-existing` 与远端哈希校验会确认已发布字节 |
| TestPyPI 失败 | 修复后重新手动运行；每次都会得到新的唯一 dev version |

### 标签前恢复

Auto Tag 的手动入口不是任意 commit 发布器。它要求：

- `source_sha` 是完整的小写 40 位 commit SHA；
- workflow definition 从默认分支运行；
- source 等于当前 `main` tip；
- 同一 source SHA 的 CI、Coverage、Prek 均成功；
- 当前版本不得低于第一父提交；
- 目标版本标签尚不存在；
- 再次完成完整分发包 preflight 后才创建标签。

标签前失败通常会在后续修复提交上表现为“当前版本与第一父提交相同”；恢复模式只为
这个场景允许相等版本。它不能用于回溯发布历史 commit，也不能覆盖已有标签。

### 标签后恢复

手动运行 Publish 时，workflow ref 必须是默认分支或与输入一致的标签。Publish
仍会重新检查标签格式、`main` ancestry、标签指向、项目版本、lockfile、构建结果及
PyPI 哈希；手动触发不会绕过发布不变量。

!!! danger "不得移动已发布标签"

    不要通过删除标签、force push 标签或重发同一版本处理部分失败。标签和 PyPI
    文件是不可变发布边界；恢复只能补齐后续状态，不能改变已经发布的字节。

## 文档版本

`main` 上的文档变更更新滚动的 `dev` 版本。正式发布从标签生成固定版本目录；
`latest` 只在目标版本不早于当前已部署最新版本时更新，因此补发旧版本不会把默认
文档回退。

Pages 部署位于软件发布链末端。若它失败，已经验证的 PyPI 和 GitHub Release 保持
有效；对同一标签重跑 Publish 即可补齐文档，无需发布新软件版本。

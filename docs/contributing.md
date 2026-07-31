# 贡献指南

欢迎提交缺陷报告、Pull Request、文档改进和使用反馈。本页描述贡献者需要遵循的
本地开发与提交工作流；GitHub Actions 的职责与远端保护规则分别见
[持续集成](ci.md)和[仓库治理](governance.md)。

## 准备开发环境

项目使用 [uv](https://docs.astral.sh/uv/) 管理 Python 与依赖。克隆仓库后执行：

```bash
git clone https://github.com/BalconyJH/aioarxiv.git
cd aioarxiv
make prepare
```

`make prepare` 会根据 `uv.lock` 同步全部依赖组，并安装
[prek](https://github.com/j178/prek) 及 Git hooks。依赖声明必须通过 uv
维护，不要直接编辑 `pyproject.toml` 中的依赖列表。

## 质量检查

提交前运行与 CI 主门禁等价的聚合命令：

```bash
make check
```

它依次检查 Ruff 格式、Ruff lint、basedpyright、公开类型完备性、ty，并行执行测试。
需要单独定位问题时可使用：

```bash
make ruff-format         # 写入 Ruff 格式化结果
make ruff-format-check   # 仅检查格式
make lint                # Ruff lint
make typecheck           # basedpyright 与公开类型完备性
make ty                  # ty 类型检查
make test                # pytest 并行测试
```

GitHub Actions workflow 还需要经过 Schema、zizmor 和 actionlint 检查。`actionlint`
位于手动 hook stage，修改 `.github/` 后应额外执行：

```bash
uv tool run prek run --all-files
uv tool run prek run actionlint --all-files --hook-stage=manual
```

## 测试

```bash
make test
```

测试由 pytest-xdist 按文件并行执行。当前布局为：

```text
tests/
|-- conftest.py         # 会话级共享 fixture
|-- test_models.py      # Pydantic 模型
|-- test_public_api.py  # 顶层公开导出
|-- test_client/        # ArxivClient 与下载器
`-- test_utils/         # 解析、会话及工具函数
```

录制的 Atom 响应等固定测试数据位于 `tests/data/`。测试不得依赖实时 arXiv
服务；网络边界应通过 fixture 或 mock 明确隔离。

## 构建分发包

发布工作流只接受经过本地同一套验证契约的 wheel 和 sdist：

```bash
make build-artifacts
```

该目标会清理 `dist/`，使用 `uv build --no-sources` 构建两种格式，执行 Twine
元数据检查，并分别在隔离环境中安装 wheel 与 sdist 后验证导入和版本。

## 文档

文档使用 [Zensical](https://zensical.org/) 构建：

```bash
make docs-serve   # 本地实时预览
make docs-build   # 严格构建，与 CI 相同
```

修改文档输入的 Pull Request 会生成临时 Pages 预览。该预览来自不受信任的 PR
内容，与正式文档共用 GitHub Pages origin；不要在该 origin 中保存 secret、
token 或可信的 `localStorage` 状态。具体信任边界见[持续集成](ci.md#docs-preview)。

## 提交 Pull Request

1. 从最新的 `main` 创建主题分支。
2. 保持变更边界清晰，并为行为变化补充测试与文档。
3. 运行 `make check`；涉及文档、打包或 workflow 时执行对应的额外验证。
4. 创建 Pull Request，说明动机、外部行为变化和验证结果。
5. 等待 `Required Checks`、`Coverage Matrix` 与 `Prek` 全部通过并解决 review。

项目只接受 squash merge。版本号提升属于发布边界，不应混入普通功能或修复 PR；
完整发布流程见[发布与恢复](release.md)。

缺陷报告请通过
[Issue Tracker](https://github.com/BalconyJH/aioarxiv/issues) 提交，并包含复现步骤、
预期行为、实际错误及最小必要的环境信息。

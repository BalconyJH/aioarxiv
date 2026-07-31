# 更新日志

本页由 `git-changelog` 根据 Git 提交记录生成。历史版本的完整发布信息仍可在
[GitHub Releases](https://github.com/BalconyJH/aioarxiv/releases) 和
[PyPI](https://pypi.org/project/aioarxiv/#history) 查看。

<!-- insertion marker -->
## [v0.2.2](https://github.com/BalconyJH/aioarxiv/releases/tag/v0.2.2) - 2026-07-31

<small>[与 v0.2.1 比较](https://github.com/BalconyJH/aioarxiv/compare/v0.2.1...v0.2.2)</small>

### 构建

- migrate project tooling to uv
  （[12440b1](https://github.com/BalconyJH/aioarxiv/commit/12440b1fed15344675c484667a3e5f849529c0ab)，
  BalconyJH）。

### 维护

- bump version to 0.2.2
  （[13ea071](https://github.com/BalconyJH/aioarxiv/commit/13ea071ce22766f495568ea5ba66938e3c34a22a)，
  BalconyJH）。

### 持续集成

- rebuild GitHub Actions and release automation
  （[347d584](https://github.com/BalconyJH/aioarxiv/commit/347d58423e014d8d9f9d45fc5bd47ffe402b8f1f)，
  BalconyJH）。

### 文档

- migrate the project site to Zensical
  （[80ca66d](https://github.com/BalconyJH/aioarxiv/commit/80ca66d592e05388002d74e798e82754a5660080)，
  BalconyJH）。

### 问题修复

- gate basedpyright on ruff
  （[633baf5](https://github.com/BalconyJH/aioarxiv/commit/633baf537511cb6f5aa443ce988a090d2ab1ce09)，
  BalconyJH）。关联 Issue/PR：[#1](https://github.com/BalconyJH/aioarxiv/issues/1)

### 代码重构

- harden client behavior and public API
  （[46d0393](https://github.com/BalconyJH/aioarxiv/commit/46d03932c2b17c26ddafd57c01346e53088e0c7d)，
  BalconyJH）。

### 其他

- :sparkles: Add SSL support with certifi in built-in session.
  （[a1f84de](https://github.com/BalconyJH/aioarxiv/commit/a1f84def7cc5e6df65ca604a5f0da002e0253f59)，
  BalconyJH）。
- :fire: Remove outdated ruff rule UP038 from pyproject.toml
  （[2e8f76a](https://github.com/BalconyJH/aioarxiv/commit/2e8f76a42a122a4a3055bcb3d9a05b5fd1a5c3c2)，
  BalconyJH）。
- :rotating_light: make ruff happy.
  （[3d36728](https://github.com/BalconyJH/aioarxiv/commit/3d36728ff6258b3ee5ec4773ea45d218f5abc482)，
  BalconyJH）。
- :heavy_plus_sign: Add certifi dependency for ssl feat in aiohttp.
  （[353f4be](https://github.com/BalconyJH/aioarxiv/commit/353f4bebf4e83e89755b2dbc1a864b2921b57b25)，
  BalconyJH）。

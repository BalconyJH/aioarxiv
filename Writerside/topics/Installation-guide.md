# Installation Guide

## Introduction

本安装指南旨在帮助用户成功安装并配置 **aioarxiv** 或作为项目依赖。

<warning>
警告：该项目目前仍处于测试阶段，尚未进入稳定版本。请勿用于生产环境。
</warning>

---

## Installation types

我们强烈建议使用如 [PDM](https://pdm-project.org/) , [Poetry](https://python-poetry.org/)
等包管理器管理项目依赖。

| **Type**  | **Description**             | **More information**           |
|-----------|-----------------------------|--------------------------------|
| PDM 安装    | 添加 `aioarxiv` 到项目依赖中。       | [跳转到安装步骤](#installation-steps) |
| Poetry 安装 | 添加 `aioarxiv` 到项目依赖中。       | [跳转到安装步骤](#installation-steps) |
| PyPI 安装   | 使用 `pip` 在支持的 Python 版本中安装。 | [跳转到安装步骤](#installation-steps) |
| 源代码安装     | 从 GitHub 克隆代码并手动安装。         | [跳转到安装步骤](#installation-steps) |

---

## Overview

### 版本信息

以下是此库的可用版本。我们暂不推荐在生产环境中依赖该库：

| **Version** | **Build**    | **Release Date** | **Status** | **Notes**             |
|-------------|--------------|------------------|------------|-----------------------|
| 0.1.1       | PyPI Release | 15/11/2024       | Latest     | Initial testing phase |

## System requirements

### 支持的操作系统

- **Windows**: Windows 10 或更高版本。
- **MacOS**: macOS 10.15 或更高版本。
- **Linux**: Ubuntu 18.04 或更高版本。

### 支持的 Python 版本

- Python 3.9 或更高版本。

## Before you begin

在安装此库之前，请确保以下事项：

- **已安装 Python**：
    - 确保您的系统中已安装支持的 Python 版本。
    - 使用 `python --version` 确认。
    - 如果未安装
      Python，请前往 [Python 官网](https://www.python.org/downloads/release/python-3920/)
      下载并安装。
- **已安装 pip**：
    - 确保您的系统中已包含 `pip` 并建议更新。
    - 使用 `pip --version` 确认版本号和使用 `pip install --upgrade pip` 更新。
- **已安装 Git**：
    - 如果您选择从源代码安装，请确保已安装 Git。
    - 使用 `git --version` 确认版本号。
- **已安装包管理器**：
    - 如果您选择使用 PDM 或 Poetry，请确保已正确安装。
    - 检查命令：
      ```bash
      pdm --version  # 检查 PDM
      poetry --version  # 检查 Poetry
      ```

## Installation steps

### PDM 安装

1. 打开命令行工具。
2. 执行以下命令以安装库：
   ```bash
   pdm add aioarxiv
   ```

### Poetry 安装

1. 打开命令行工具。
2. 执行以下命令以安装库：
   ```bash
   poetry add aioarxiv
   ```

### 使用 pip 从 PyPI 安装

1. 打开命令行工具。
2. 执行以下命令以安装库：
   ```bash
   pip install aioarxiv
    ```

### 源代码安装

1. 打开命令行工具。
2. 执行以下命令以克隆代码：
   ```bash
   git clone https://github.com/BalconyJH/aioarxiv.git
   cd aioarxiv
   pip install .
   ```
   
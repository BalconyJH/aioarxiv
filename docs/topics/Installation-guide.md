# Installation Guide

## Introduction

This installation guide is designed to help users successfully install and configure **aioarxiv** or add it as a project
dependency.

---

## Installation types

We strongly recommend using package managers like [PDM](https://pdm-project.org/)
or [Poetry](https://python-poetry.org/) to manage project dependencies.

| **Type** | **Description**                                      | **More information**                                                                    |
|----------|------------------------------------------------------|-----------------------------------------------------------------------------------------|
| PDM      | Add `aioarxiv` to project dependencies.              | <a href="Installation-guide.md#installation-steps_pdm">PDM Installation Steps</a>       |
| Poetry   | Add `aioarxiv` to project dependencies.              | <a href="Installation-guide.md#installation-steps_poetry">Poetry Installation Steps</a> |
| UV       | Install using `uv` for faster dependency resolution. | <a href="Installation-guide.md#installation-steps_uv">UV Installation Steps</a>         |
| PyPI     | Install using `pip` in supported Python versions.    | <a href="Installation-guide.md#installation-steps_pypi">PyPI Installation Steps</a>     |
| Source   | Clone from GitHub and install manually.              | <a href="Installation-guide.md#installation-steps_source">Source Installation Steps</a> |

---

## Overview

### Version Information

Below are the available versions of this library. We do not recommend relying on this library in production environments
at this time:

| **Version** | **Build**                                                | **Release Date** | **Status** | **Notes**                                       |
|-------------|----------------------------------------------------------|------------------|------------|-------------------------------------------------|
| 0.2.1       | [PyPI Release](https://pypi.org/project/aioarxiv/0.2.1/) | 03/04/2025       | Latest     | Documentation updates and new search experience |
| 0.2.0       | [PyPI Release](https://pypi.org/project/aioarxiv/0.2.0/) | 13/01/2025       | Old        | Bug fixes and improvements                      |
| 0.1.2       | [PyPI Release](https://pypi.org/project/aioarxiv/0.1.2/) | 15/11/2024       | Old        | Initial release                                 |

## System requirements

### Supported Python Versions

- Python 3.9 or higher.

<tip>
Ensure your Python version is within the supported range before installing this library.
</tip>

## Installation steps

<tabs>
    <tab title="PDM Installation" id="installation-steps_pdm">
        <p>To install aioarxiv using PDM:</p>
        <procedure>
            <step>Open your terminal</step>
            <step>
                Run the following command:
                <code-block lang="bash">
                    pdm add aioarxiv
                </code-block>
            </step>
        </procedure>
    </tab>
    <tab title="Poetry Installation" id="installation-steps_poetry">
        <p>To install aioarxiv using Poetry:</p>
        <procedure>
            <step>Open your terminal</step>
            <step>
                Run the following command:
                <code-block lang="bash">
                    poetry add aioarxiv
                </code-block>
            </step>
        </procedure>
    </tab>
    <tab title="PyPI Installation" id="installation-steps_pypi">
        <p>To install aioarxiv using pip:</p>
        <procedure>
            <step>Open your terminal</step>
            <step>
                Run the following command:
                <code-block lang="bash">
                    pip install aioarxiv
                </code-block>
            </step>
        </procedure>
    </tab>
    <tab title="UV Installation" id="installation-steps_uv">
        <p>To install aioarxiv using uv:</p>
        <procedure>
            <step>Open your terminal</step>
            <step>
                Run the following command:
                <code-block lang="bash">
                    uv add aioarxiv
                </code-block>
            </step>
        </procedure>
    </tab>
    <tab title="Source Installation" id="installation-steps_source">
        <p>To install aioarxiv from source:</p>
        <procedure>
            <step>Open your terminal</step>
            <step>
                Clone the repository and install:
                <code-block lang="bash">
                    git clone https://github.com/BalconyJH/aioarxiv.git
                    cd aioarxiv
                    pip install .
                </code-block>
            </step>
        </procedure>
    </tab>
</tabs>

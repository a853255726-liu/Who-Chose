# WhoChose

**Who chose what your AI built?**

WhoChose 让使用 AI 编程的用户审阅本次实现中的重要选择：做了什么、要求来自哪里、为什么这样实现，以及对应的真实代码位置。

版本 **0.1.2**。独立本地 Python 项目，优先面向支持本地插件和命令 Hook 的 Windows Codex 桌面宿主。Python 3.11+。

## 功能

- 按功能汇总重要决定，区分用户要求、AI 自主选择和来源未确定。
- 项目说明保留要求效力，明确引用说明文件、原文及版本；不冒充当前聊天中的用户原话。
- 把实际代码变化关联到选择，普通调整按功能块汇总。
- 在编辑前采集受限基线，交付时显式检查覆盖；缺口和未审阅变化保留可见。
- 等待用户回复时可直接结束本轮，Stop 不触发审阅续轮。
- 生成可离线打开的单文件 HTML 审阅报告，也支持 Markdown 导出。

## 安装

```powershell
git clone https://github.com/a853255726-liu/Who-Chose.git
cd Who-Chose
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m whochose.cli doctor
.\.venv\Scripts\python.exe -m whochose.cli package --output dist\manual-0.1.2 --python .venv\Scripts\python.exe
```

将准备好的本地 marketplace 安装到支持的 Codex 宿主，再审阅并信任 Hook。具体步骤见 [安装与使用](docs/INSTALL.md)。插件模板需要先运行 `package`，以生成当前电脑的解释器与启动路径。

## 使用方式

启用插件后，可让 Agent 使用以下 Skills：

1. `capture-decisions`：记录有原文依据的明确要求、接受的方案、范围授权或项目说明引用。
2. `review-plan`：实现前只澄清重要的未决选择。
3. `trace-implementation`：关联实际变化，交付时检查并完成任务。

编码前建立任务基线；跨会话沿用同一 `task_id`。`scope` 使用相对文件或目录，例如 `src`、`README.md`；不支持 `ui/**`、`test_*.py` 等模式。已完成任务冻结结果，之后的改动不计入旧任务。

报告默认写到目标项目的 `whochose-review.html`。界面只用于审阅和复制代码位置，没有批准、回滚或自动修改入口。

## 本地数据与证据边界

SQLite 是记录的主数据源。Windows 默认存于 `%LOCALAPPDATA%\WhoChose`；可通过 `WHOCHOSE_DATA` 或 CLI `--data-root` 指向被跟踪工作区之外的目录。

消息 Hook 只保留有界原文前缀与哈希。快照排除私密目录、敏感内容、二进制、大文件和链接，无法检查的内容保留缺口。程序校验引用、路径和版本，不自动验证自然语言意图。

开发时理由、事后分析、代码推断与实际运行证据分别记录。保存决定不等于用户批准宿主操作。没有可信消息 Hook 时，不可伪造聊天确认；适用的项目文档可以作为独立引用来源。

项目不提供云端同步或自动上传。仓库只包含运行代码、插件模板和必要使用说明。

## 目录

- `whochose/`：Python 运行库、MCP 服务、CLI 和离线审阅模板。
- `plugins/whochose/`：插件 manifest、MCP/Hook 模板与三个 Skills。
- `docs/INSTALL.md`：安装、使用与卸载说明。

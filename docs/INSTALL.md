# 安装与使用

## 准备本地插件

在源码根目录使用 Python 3.11+：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m whochose.cli doctor
.\.venv\Scripts\python.exe -m whochose.cli package --output dist\manual-0.1.2 --python .venv\Scripts\python.exe
```

`package` 将运行库与插件模板放入新的版本目录，生成当前电脑的绝对解释器路径、启动脚本、Windows Hook 命令和本地 marketplace。输出目录必须尚不存在。此命令不会安装插件、修改宿主配置或自动信任 Hook。

可选 `--runtime-data <工作区之外的数据目录>` 同时指定 MCP 与 Hook 的数据目录。准备好的目录与解释器需要保留；换电脑或移动解释器后应重新准备。

## 注册与信任

使用支持本地插件及命令 Hook 的 Codex 宿主。先检查实际使用的 CLI 与桌面宿主是否匹配：

```powershell
codex --version
codex plugin marketplace add --help
codex plugin add --help
```

支持这些命令的版本可执行：

```powershell
codex plugin marketplace add .\dist\manual-0.1.2
codex plugin add whochose@whochose-local
```

也可通过宿主插件管理界面添加准备结果的本地 marketplace 并安装 `whochose`。已有同名本地 marketplace 时，应先在宿主配置中更新其来源路径。

启用插件并不表示 Hook 已受信任。请在宿主界面审阅当前 Hook 定义和脚本；升级后内容变化可能需要重新信任并重载。插件使用 UserPromptSubmit、PostToolUse 和 Stop 回调；Stop 仅结束本轮，不阻断等待回答。

## 日常使用与手动回退

开始编辑前启动 WhoChose 任务；已有任务用同一个 `task_id` 恢复。范围只接受工作区内的相对文件或目录，不支持 glob 模式。Hook 提供的消息引用用于校验聊天原话；项目要求使用项目文档的路径、SHA256 和原文单独引用。

任务交付前显式检查变化覆盖并执行 complete，保留缺失证据与范围限制。需要等待用户时直接结束本轮并保留任务未完成状态。

```powershell
# 替换为真实任务 ID
.\.venv\Scripts\python.exe -m whochose.cli report --task <task_id> --format html
.\.venv\Scripts\python.exe -m whochose.cli export --task <task_id> --format md

# 显式调用与 MCP 相同的业务入口；JSON 文件应为 UTF-8
.\.venv\Scripts\python.exe -m whochose.cli call get_task_context --input start.json
```

`start.json` 包含 workspace_root、action=start、scope、description 与稳定且唯一的 idempotency_key。后续调用使用服务实际返回的任务和变化引用，不自行构造消息、记录或 hunk ID。

没有消息 Hook 时，聊天确认引用不可伪造。可记录有依据的 AI 选择、来源未知项或适用的项目说明引用，并手动执行覆盖检查。

## 数据与卸载

默认 Windows 数据根是 `%LOCALAPPDATA%\WhoChose`；其他系统使用用户数据目录。数据根必须在被跟踪工作区之外。数据包含 SQLite 和受限版本快照，应按个人项目资料保管。

在宿主中禁用或卸载 `whochose@whochose-local` 后，再处理准备好的版本目录。卸载插件不自动清除历史数据；需要保留记录时先导出并备份数据根。

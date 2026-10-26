# 自动化示例

示例仅使用已观察到的原始状态变化，不控制设备，不认定洗涤正常完成。
它不会随安装自动启用，需要你自己创建自动化。

## 上报进入工作状态

打开设备的“状态”实体设置，复制实际实体 ID；不要使用“设备上报程序”或“设备上报进程”。
进入 **设置 → 自动化与场景 → 创建自动化 → 新建空自动化 → ⋮ → 使用 YAML 编辑**，
粘贴 [examples/reported-working.yaml](../examples/reported-working.yaml) 的内容，
将 `sensor.replace_with_your_minij_status` 替换为你的状态实体 ID 后保存。

该示例仅当上报值从 `resting` 变为 `working` 时创建 HA 内部通知。
不会仅因进程显示“主洗”或“脱水”触发，不会因普通恢复为 `working` 而从未知/不可用误报启动。
如果 HA 启动时设备已经运行，或云端轮询漏掉了中间变化，可能不会触发。
通知表达的是云端状态变化，不承诺精确启动时间；轮询间隔为 60 秒。

目前不提供 `working → resting` 的完成示例：正常完成、取消和停止尚未区分。
云端不可用也不能当作物理断网或机器关机。

示例经过 HA 配置结构检查，但未在用户生产环境创建或执行。
依据：[HA 状态触发器](https://www.home-assistant.io/docs/automation/trigger/)。

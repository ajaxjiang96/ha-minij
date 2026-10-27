# 通知蓝图与自动化示例

蓝图和完成示例使用独立的官方消息；基础状态示例使用已观察到的原始状态变化。
均不控制设备，也不通过回空闲或剩余时间归零推断完成。
它不会随安装自动启用，需要你自己创建自动化。

## 0.5：通过界面配置通知蓝图

[小吉完成与故障通知蓝图](../blueprints/automation/minij/device-notification.yaml)
支持官方 `wash_completed`（洗衣完成）、`cleaning_completed`（筒清洁完成）、
`fault_reported`（故障提醒）消息，可选择任意一种或多种；至少保留一种。
蓝图复用 `0.4.0b5` 已有事件，不需要升级集成或重启 HA；不会创建洗涤控制。

1. 打开 **设置 → 自动化与场景 → 蓝图 → 导入蓝图**。
   粘贴下方 GitHub 文件地址并预览、导入。PR 合并前，该 `main` 地址尚未包含新文件；
   可先下载 PR 中的文件，放到 HA 配置目录的
   `blueprints/automation/minij/device-notification.yaml`，再刷新蓝图列表。

   ```text
   https://github.com/ajaxjiang96/ha-minij/blob/main/blueprints/automation/minij/device-notification.yaml
   ```

2. 从该蓝图创建自动化，选择目标洗衣机的 **设备通知** 事件实体和通知类型。
   选择器只列出 MiniJ 的事件实体；若没有选项，先确认该设备已提供“设备通知”实体。
   当前事件能力只在 `minij.washer.x68` 提供，不代表所有型号均支持。
3. 默认动作是在 HA 内部创建通知，不要求安装手机 App。
   若要手机推送，在“收到消息后执行”中删除默认动作，再添加手机 App 的通知动作，
   选择自己的手机；标题填写 `{{ minij_title }}`，消息填写 `{{ minij_message }}`。
   手机须事先通过 HA Companion App 接入并允许通知。以上字段在可视化编辑器中填写，无需改 YAML。
   如需同时推送和 HA 内部通知，可保留默认动作并添加手机动作。
4. 给自动化命名并保存启用。每台洗衣机单独创建一份，避免混淆来源。
   保存、重载和重启不会把历史完成事件重发；下次收到新的官方消息才触发。

可选自定义动作还能读取 `minij_event_type`、`minij_notification_entity`。
默认 HA 通知按“来源实体＋事件类型”更新同一通知；手机通知是否合并由所选渠道决定。
不同洗衣机和不同消息类型的默认通知互不覆盖。故障通知只提示查看机器和 App，不猜测故障原因。

蓝图不重复推断周期或增加消息轮询，继承集成的消息去重和恢复基线：
首次读取、重启与故障恢复不补报旧消息，云端或 HA 停机期间可能漏报；不能承诺每个周期恰好送达一次。
可视化编辑器的“运行动作”没有真实事件 `trigger`，不适合验证本蓝图。
调试请查看自然收到消息后的自动化轨迹；不要为了测试发消息或额外启动洗涤。

[蓝图结构](https://www.home-assistant.io/docs/blueprint/schema/)与
[动作选择器](https://www.home-assistant.io/docs/blueprint/selectors/#action-selector)
使用 HA 标准机制。运行回归使用隔离 HA 和合成事件；未向真实手机推送或操作机器。
配套卡片见[仪表盘模板](dashboard.md)。

## 手动 YAML 示例

### 上报进入工作状态

打开设备的“状态”实体设置，复制实际实体 ID；不要使用“设备上报程序”或“设备上报进程”。
进入 **设置 → 自动化与场景 → 创建自动化 → 新建空自动化 → ⋮ → 使用 YAML 编辑**，
粘贴 [examples/reported-working.yaml](../examples/reported-working.yaml) 的内容，
将 `sensor.replace_with_your_minij_status` 替换为你的状态实体 ID 后保存。

该示例仅当上报值从 `resting` 变为 `working` 时创建 HA 内部通知。
不会仅因进程显示“主洗”或“脱水”触发，不会因普通恢复为 `working` 而从未知/不可用误报启动。
如果 HA 启动时设备已经运行，或云端轮询漏掉了中间变化，可能不会触发。
通知表达的是云端状态变化，不承诺精确启动时间；轮询间隔为 60 秒。

不提供基于 `working → resting` 的完成示例：取消和停止仍未逐项区分；
完成示例使用独立官方消息，见下文。
云端不可用也不能当作物理断网或机器关机。

示例经过 HA 配置结构检查，但未在用户生产环境创建或执行。
依据：[HA 状态触发器](https://www.home-assistant.io/docs/automation/trigger/)。

### 上报进入异常状态

[examples/reported-exception.yaml](../examples/reported-exception.yaml) 仅在原始状态
从 `resting` 或 `working` 变为 `device_exception` 时创建 HA 内部通知。
同样先替换实际状态实体 ID，再由用户自行保存启用。
首次报告异常、未知/不可用恢复为异常和同状态重复轮询不会触发。
同一状态实体重复进入异常时复用通知 ID；不同实体的通知分开。

这表示云端上报变化，不诊断故障，不代表机器物理离线。
HA 重载/离线期间的变化可能漏掉；没有历史事件接口，不能补报或保证完整送达。
示例已通过真实 HA 状态触发器回归，未在用户生产 HA 中创建或执行。

### 剩余时间自动化边界

剩余分钟数是云端估计，每次读取更新，可能停留或调整；不是本地秒级倒计时。
不要以 `0`、未知、不可用或 `working → resting` 单独触发“正常完成”。
完成通知使用下方官方消息事件，不依赖时间字段。

### 官方完成消息

[examples/program-completed.yaml](../examples/program-completed.yaml) 使用“设备通知”
事件实体。将占位 `event.replace_with_your_minij_device_notification` 替换为实际事件实体 ID，
自行保存启用；不是原来的状态传感器 ID。
它通过 HA 的 `event.received` 匹配 `wash_completed`、`cleaning_completed`，
不会因为状态恢复了上次事件时间而通知，也不依赖运行回空闲或剩余时间归零。

本功能读取官方“洗衣完成／清洁完成”消息。不同物理周期如果厂商重用 ID，或一个周期产生多个 ID，
不能由集成推断出完美的周期身份。停机/故障/重载窗口和默认消息页外可能漏报，
恢复第一份列表不补发旧消息。事件时间是 HA 处理时间，不是精确结束时刻。
代码及标准触发器已有合成回归；真实设备的新消息交付需在候选安装后正常使用中验收。

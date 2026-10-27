# 0.4.0b2 本地控制验收版

本版按所有者要求直接本地安装，不创建 GitHub Release 或发布标签。
不再按 `resting/waiting/working`、型号、固件或“云端授权”上报字段提前拒绝控制。
服务端自己的认证、设备保护和命令拒绝仍由服务端处理；失败会在 HA 报错。

## 本次可以测试的控制

| 控制 | 请求与取值依据 | 当前验证范围 |
| --- | --- | --- |
| 童锁 | 原生 childLock 布尔路径 | 已发送但未确认效果，面板存在；所有者下次洗涤核对 |
| 提示音 | App 更多设置的 promptTone | waiting 已有实际静音/解除与恢复记录；其他状态待测 |
| 程序选择 | 本机程序列表 + deviceModeSetup | 本机只读发现 22 个程序；选择后的真实行为待测 |
| 洗涤水位、温度、漂洗次数、烘干、烘干强度、蒸汽除菌、UVC 筒灯 | 当前程序的 optionalValueList + workingUserStatsSetup | 全部 22 程序只读发现参数并集 7 项；逐项写入效果待测 |
| 清洁提醒、托管（设备提供时）、提醒次数 | 智能清洁网页及本机元数据 | 本机提供提醒及 5–50 次的选项，托管字段为 null，App 隐藏 |
| 立即筒清洁 | 网页 immediateExecBucketClean 原样参数 | 仅单次请求并记录云端接受；不将 ACK 说成机器已运行 |

参数项随所选程序变化；不支持的参数显示不可用、选项清空。温度等是协议枚举：
例如“40℃”对应值 3，不能把数字 40 直接当协议值。输入必须在设备最新提供的选项里。
这是参数正确性检查，不是人为限制运行状态。切换程序后不会继续使用先前程序的参数 ID。

普通洗涤的启动/暂停/继续/取消/电源动作仍缺准确 operateType 取值，
本版不把猜测字符串包装成可用按钮。立即筒清洁是独立且已确认载荷的网页路径，
不能当作通用洗涤启动。程序选择端点与启动路径分开，但程序选择后的实际机器行为仍待所有者核对。

## 本地安装与回退

部署前在 HA 本地备份现有 `custom_components/minij` 和实体注册表副本。
替换仅针对 MiniJ 目录，保留账号配置、实体身份和已有自动化；重启 HA 后核对加载版本。
原先已被 HA 注册为禁用的控制通过 HA 界面启用，不通过运行时迁移重写用户偏好。

回退时恢复备份中的 MiniJ 目录并重启。不要从 HACS 再次下载旧版本覆盖本地验收代码，
除非明确要回退。HACS 的下载版本记录与本地 manifest 版本可能不同，验收以运行的 manifest 为准。

## 测试与 Diagnostics

所有设备指令由所有者按自己的顺序操作；安装、加载、发现程序和下载诊断不会自动操作机器。
每个控制请求最多发送一次，允许少量读回确认；不自动重发未知结果。
“请求被云端接受”与“机器已执行”分开记录，实体状态来自实际读取。

每批操作后直接下载 MiniJ 的 Diagnostics，再反馈机器/App 的实际表现。
**先下载再重启**：最近 30 条控制台账只保留于本次集成加载期间，重启/重载会清空。
台账包含时间、功能、目标值、请求前缓存状态、响应分类和耗时，不包含令牌、手机号、
设备/账号/程序/参数 ID、原始响应或错误正文。设备设置和程序选项是缓存摘要，下载不额外轮询。
这些记录帮助比对“界面操作→云端接受/拒绝→稍后上报→机器观察”，不能单凭 ACK 判定功能成功。

## 协议证据

- 程序读取：GET device/v2/getDeviceModeList（deviceId、空 bucketCode）。
- 参数读取：GET device/v2/getUserDeviceMode（deviceId、currentDeviceMode.id）。
- 程序写入：POST device/deviceModeSetup，deviceId/userDeviceModeId 为字符串，bid/vid/programNum 为整数。
- 单参数写入：POST device/v2/workingUserStatsSetup，deviceId/basicFunction/value/userDeviceModeStatsId 均为字符串。
- 批量 deviceStatsSetup 内部 map 键尚未确定，没有用猜测 map 取代单参数路径；是否在非运行状态接受由实际服务端结果核对。
- 智能清洁：GET device/getIntelligentBucketClean；POST device/switchBasicFunction、device/remindAfterCleanTimes、device/immediateExecBucketClean。
- 立即清洁的 deviceModeId 原样来自元数据，包含本机的 null；网页本身仍显示按钮，是否执行需真实验收。

原始抓包和私有元数据仅保留本机忽略目录。REA 静态分析与只读 API、合成 HA 回归、
实际部署和设备写入验收分别记录，不将其中一种证据替代另一种。

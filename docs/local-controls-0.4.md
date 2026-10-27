# 0.4.0b4 本地控制验收版

本版按所有者要求直接本地安装，不创建 GitHub Release 或发布标签。
不再按 `resting/waiting/working`、型号、固件或“云端授权”上报字段提前拒绝控制。
服务端自己的认证、设备保护和命令拒绝仍由服务端处理；失败会在 HA 报错。

## 本次可以测试的控制

| 控制 | 请求与取值依据 | 当前验证范围 |
| --- | --- | --- |
| 童锁 | 原生 childLock 布尔路径 | 本次诊断含 working 状态开/关后的云端上报变化；面板效果未单独确认 |
| 提示音 | App 更多设置的 promptTone | waiting 已有实际静音/解除与恢复记录；其他状态待测 |
| 唤醒（实验） | 原生菜单“开机”的 power_on | 断网生成的准确请求已观察；真实设备效果待所有者验收 |
| 启动待选程序（实验） | 原生程序详情“立即运行”的 activate | 按所选程序 ID 单次发送，未修改参数时的原生空参数列表；真实启动待验收 |
| 待启动程序 | 本机程序列表 + 目标程序参数读取 | 本地选择草稿，不发送设备命令；不同程序参数已只读核对 |
| 洗涤水位、温度、漂洗次数、烘干、烘干强度、蒸汽除菌、UVC 筒灯 | 当前程序的 optionalValueList + workingUserStatsSetup | 全部 22 程序只读发现参数并集 7 项；所有者反馈多项有效，未逐项确认 |
| 清洁提醒、托管（设备提供时）、提醒次数 | 智能清洁网页及本机元数据 | 本机提供提醒及 5–50 次的选项，托管字段为 null，App 隐藏 |
| 立即筒清洁 | 网页 immediateExecBucketClean 原样参数 | 仅单次请求并记录云端接受；不将 ACK 说成机器已运行 |

“待启动程序”仅保存在本次加载期间，重启后重新使用云端目录初值。它不代表机器已切换或启动，实际程序仍看“设备上报程序”传感器。
切换时先读取目标参数，成功后整组替换；读取失败保留旧选择和参数。后台刷新保留草稿，Diagnostics 单独标明 `selection_source` 和 `cloud_catalog_current`。

参数项随所选程序变化；不支持的参数显示不可用、选项清空。温度等是协议枚举：
例如“40℃”对应值 3，不能把数字 40 直接当协议值。输入必须在设备最新提供的选项里。
这是参数正确性检查，不是人为限制运行状态。切换程序后不会继续使用先前程序的参数 ID。

普通唤醒和启动已经取得原生 App 的准确动作值，分别使用 `power_on` 和 `activate`。
先选“待启动程序”，核对下方参数，再显式按“启动待选程序（实验）”。启动不会自动调用唤醒，
不会重发，也不把云端接受改成“运行中”。要只唤醒则单独按“唤醒（实验）”。
程序草稿初值可能是云端目录保留的上次程序，启动前应明确选一次所需程序。

本次观察到：联网只读加载完整标准程序详情后，断网点“立即运行”，
`activateParam.userDeviceModeStatsSimpleList` 仍为 `[]`。本版复现这条“启动已保存程序”的路径，
不拼接未经观察的参数映射。已有参数控制保留单参数写入；它们与实际启动效果的关联仍需设备验收。
暂停、继续、取消和关机尚未取得准确动作值；不会将通知专用 activateCode 或筒清洁接口作为普通启动。

旧版 `deviceModeSetup` 虽被云端接受，目录当前项却未随之变化；
它不能证明交互式程序切换，已删除该写入路径，改为明确的待启动草稿。

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
- 参数读取：GET device/v2/getUserDeviceMode（deviceId、所选程序 ID）；不能固定读目录旧 currentDeviceMode.id。
- 选择草稿：只读目标程序参数并更新本地完整快照，无程序写入请求。
- 唤醒：POST device/v2/deviceOperate，`{deviceId, bucketCode: "", operateType: "power_on"}`。
- 启动：同一路径，`operateType: "activate"`，另带 `activateParam: {userDeviceModeId, userDeviceModeStatsSimpleList: []}`。
- 单参数写入：POST device/v2/workingUserStatsSetup，deviceId/basicFunction/value/userDeviceModeStatsId 均为字符串。
- 批量 deviceStatsSetup 内部 map 键尚未确定，没有用猜测 map 取代单参数路径；是否在非运行状态接受由实际服务端结果核对。
- 智能清洁：GET device/getIntelligentBucketClean；POST device/switchBasicFunction、device/remindAfterCleanTimes、device/immediateExecBucketClean。
- 立即清洁的 deviceModeId 原样来自元数据，包含本机的 null；网页本身仍显示按钮，是否执行需真实验收。

原始抓包和私有元数据仅保留本机忽略目录。REA 静态分析与只读 API、合成 HA 回归、
实际部署和设备写入验收分别记录，不将其中一种证据替代另一种。

# 程序保存参数与启动覆盖研究

更新于 2026-11-07。对应 [Issue #29](https://github.com/ajaxjiang96/ha-minij/issues/29)。
本记录区分社区客户端反馈、V6-XNB 历史读取和 Android App 静态路径；不改变集成控制行为。
最新进展：已从独立离线模拟器内存恢复业务 DEX，并由 App 模型和 Rust 核心离线生成五种合成请求，
确认启动列表的字段结构和独立详情参数路径。随后经所有者授权，仅在待机状态核对参数接口：
请求被接受，但三次读取均未观察到保存值变化，最终原值已确认；启动覆盖是否保留默认值仍待验证。

## 社区反馈：U10 Pro

报告设备为 U10 Pro 内裤洗烘一体机，云端型号 `minij.pants.x1`，带自动投放。
报告者基于本项目协议编写了独立客户端，接入自己的 AI 助手，未使用本 HA 集成。
其反馈短信登录、设备列表、状态/程序查询、启动、停止、启动后叠加烘干和通知查询可用。
这属于社区对云端协议的使用反馈，不能据此标记本 HA 集成已完成 U10 Pro 验收。

报告者观察到：App 使用一次“日常洗＋烘干”后，仅指定日常洗启动，仍沿用先前的烘干设置；
启动后写入 `dryingCompoundOption=2` 可叠加即穿，烘干阶段暂停被服务端拒绝。
这些观察尚未由维护者在 U10 Pro 上复现，不推广为其他型号的枚举或阶段规则。

### 报告者补充的日常洗元数据

[后续评论](https://github.com/ajaxjiang96/ha-minij/issues/29#issuecomment-6689243961)
提供了已脱敏的 `getUserDeviceMode` 烘干项：`type=choose`、当前 `value=0`，选项如下。
这是 U10 Pro 的日常洗数据，不是所有程序的共同参数表。

| 标签 | U10 Pro 日常洗 | V6-XNB 标准程序的历史值 |
| --- | --- | --- |
| 无烘干 | 0 | 0 |
| 即穿 | 2 | 2 |
| 特干 | 3 | 此前元数据未提供 |
| 30分钟 | 5 | 4 |
| 60分钟 | 6 | 5 |
| 90分钟 | 7 | 6 |
| 120分钟 | 8 | 7 |

报告者说明：此前即穿任务约 135 分钟，但当时未单独读取此项；2026-11-05 晚上在 App
改为不烘干后，现在读取为 `0`，没有为补充记录额外启动洗涤。
因此没有成对的修改前／后字段快照或对应请求，不能据此认定设置在哪一步保存，
也不能声称启动时单次覆盖已通过。

已将这份元数据与 V6-XNB 标准程序的烘干选项整理为
[`drying_parameters.json`](../tests/fixtures/drying_parameters.json)，所有参数项 ID 均为合成值。
回归覆盖同名“30分钟”的不同数值、U10 Pro 的“特干”、显式关闭值 `0`，
以及命令预读后采用新元数据的枚举和参数身份；均使用模拟客户端，不连接真实设备。
此类解析／选择测试不替代 U10 Pro 的 HA 安装与实际控制验收。

## 当前启动与参数写入

集成的 `MinijClient._program_command` 发送 `device/v2/deviceOperate`：

```json
{
  "deviceId": "synthetic-device",
  "bucketCode": "",
  "operateType": "activate",
  "activateParam": {
    "userDeviceModeId": "synthetic-program",
    "userDeviceModeStatsSimpleList": []
  }
}
```

此前在 V6-XNB 的原生 App 中，只读加载完整程序详情后断网点击“立即运行”，
生成的列表仍为空。这仅覆盖当时没有修改详情选项的路径。
空列表没有显式写入“不烘干”，不能将它当作清空、恢复默认或只洗涤的指令。
社区反馈与沿用已有参数的解释吻合；保存位置、服务端默认规则仍未确认。

现有参数选择另行调用 `device/v2/workingUserStatsSetup`，字段为
`deviceId`、`basicFunction`、字符串 `value` 和 `userDeviceModeStatsId`。
接口名称不能证明它只影响当前运行，也不能证明它不会持久化。
HA 参数选择会立即尝试写入；“待启动程序”的选择本身则只是本地草稿。

## 我们自己的枚举证据

重新检查本机保留的 V6-XNB 历史只读程序详情，22 个程序记录中有 20 个包含
`dryingCompoundOption`。例如标准、快洗和婴童的烘干选项包括：

| 返回标签 | 返回值 |
| --- | --- |
| 无烘干 | 0 |
| 即穿 | 2 |
| 30 / 60 / 90 / 120 / 150 / 180 分钟 | 4 / 5 / 6 / 7 / 8 / 9 |

这是 V6-XNB 当时返回的元数据，不是本轮新发生的物理验证。
U10 Pro 仍需以自己的 `optionalValueList` 为准；不因两个型号都提及即穿就假定全部枚举相同。
程序参数身份必须从目标程序重新读取，不能跨程序复用。

同一台机器也存在程序差异：本批数据的“单烘干／低温烘”没有“无烘干”，
“筒自洁”仅提供“无烘干／30分钟”，“空气洗”仅提供 30–180 分钟。
因此即使已经确认型号，也必须按所选程序返回的元数据校验组合，不能套一张型号级固定枚举表。

## 原生启动列表的静态线索

分析目标为已保存 APK 1.7.1（111）中的 AArch64 `libbloc.so`，SHA-256：
`d5acc1f30c00aff1f6d4bbaf0d39f0cc45077ed6572a17becaea5fb6010f76a9`。
本轮复用原生反汇编，并用 Xcode LLVM objdump 读取相关序列化函数；没有声称取得 Java/Kotlin 原始源码。

- `Device::update` 在 `0x4a9e34` 构造 `activateParam`；`0x4a9e68` 的字符串切片与
  长度 16 对应 `userDeviceModeId`。
- `0x4a9f20` 至 `0x4a9f34` 构造长度 29 的 `userDeviceModeStatsSimpleList` 键。
  随后检查传入列表的 Option/Vec 表示，非空分支在 `0x4aa238` 读取事件数据，
  `0x4aa254` 调用 `Serializer::collect_seq`（`0x546670`）。
- 该序列化函数在 `0x54672c` 逐项调用 `collect_map`（`0x545a28`），
  并非无条件构造空数组；此阶段尚未从界面调用方确认映射元素，后续结果见下文。

此阶段确认原生启动组装路径支持由调用方提供列表，尚未确认哪些洗衣机界面会填入它、
列表元素的业务结构，以及服务端对非空列表的处理。
**存在列表参数不等于已证明“只覆盖本次且不改变保存值”。**

现有网页资源目录的有界搜索未找到上述烘干和启动列表字面量；
这不说明全部网页版本或服务端没有对应能力。

## 本轮运行取证边界

恢复已有 Android 模拟器后，先停止 App 并关闭网络，再启动 App。
随后按所有者此前授权临时联网，仅加载页面；设备列表未成功显示，未进入程序详情。
本轮未取得“修改烘干选项后再启动”的新请求，没有发送设备控制、短信或固件更新。
结束临时联网后再次关闭 Wi-Fi/移动数据和启用飞行模式。

REA 的本轮 ADB 初始发现证据为
`ev_89a467d44b7a344ba4f9d25c293773db7a7df840f0c8fe757c035679994d6a94`：
当时没有连接的设备；后续模拟器恢复和页面检查使用普通 ADB，不归于此 Evidence ID。
本机 REA 的 JADX headless provider 仍不可用，不能据此声称完成 Android 反编译。
原始日志和元数据仅保留在忽略目录 `analysis/`，不提交账号或设备标识。

所有者随后授权仅对本地模拟器执行 `adb root`、读取 App `.jiagu` 代码目录。
系统返回 `adbd cannot run as root in production builds`；标准 `run-as` 也返回
`package not debuggable`。构建类型为 `user`、`ro.debuggable=0`；本机仅有
Android 36 Google Play 镜像，没有其他已安装的可调试系统镜像。
因此本轮没有取得保护壳释放的代码，授权本身不能替代成功读取的证据。
进一步分析该代码需要另建可调试环境；不能把本次失败描述成服务端不支持参数覆盖。

### 后续：独立可调试模拟器已建立

2026-11-07 所有者接受官方镜像条款后，创建独立 Android 16 / API 36
Google APIs ARM64 v8a revision 7 环境，包名为
`system-images;android-36;google_apis;arm64-v8a`，不含 Play Store。
官方镜像归档 SHA-1 核对为 `5a99183b6d924da606260e45fd41a3eb8eca6eb7`，
本机 SHA-256 为 `fb47d861d6f87230ee0fe70f610d579935ca77f41a0eefbf391595d3dc4b5ee2`。

新环境实际启动后返回 `ro.build.type=userdebug`、`ro.debuggable=1` 和 `uid=0(root)`。
使用独立 AVD 数据目录和端口，保留原生产镜像环境，未复制任何账号数据。
离线安装并启动用户提供的同一 APK；App 停在首次用户协议／隐私政策提示，未登录、未操作设备。

本次获准读取的 `.jiagu` 目录内仅提取到 `libjiagu_64.so`（932704 字节，SHA-256
`ba53108eec6c9a7daf032db41d72ae8bf5efc5df4f66d52c250b55d445d22a32`），
`oat/arm64` 目录为空，未发现业务 DEX。root 和目录访问已经验证，
但不能据此声称已恢复业务代码或证明启动覆盖语义；保护壳提取与后续代码取证仍需继续研究。

镜像信息来自 [Google 官方 SDK 清单](https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-3.xml)。
[Android 官方 AVD 说明](https://developer.android.com/studio/run/managing-avds)
解释了含 Play Store 的发行镜像不可取得 root；这里对非 Play 镜像的 root 结论另有本机实际验证。

## 后续：内存 DEX 与业务参数契约

在同一个无账号、断网的独立模拟器中，仅启动 App 至首次协议提示页，未接受 App 条款。
读取该 App 的进程映射后，对匿名可读映射开头做 DEX 文件头探测；43 个候选中 3 个有 DEX 头。
只导出这 3 个已识别的代码映射，不导出普通堆；其中一个映射中包含多个按页对齐的 DEX，
最终恢复 7 个具有有效长度、文件头和 endian tag 的 DEX。

7 个文件的 Adler-32 与文件头匹配，但内置 SHA-1 signature 均不匹配；
它们是保护壳加载后的内存代码，不是经过原 APK 签名验证的原始 DEX。
每份导出另行计算 SHA-256 留存。JADX 1.5.3 对业务 DEX 的批处理退出为 1，报告 52 个错误，
因此不把整份反编译当作无损源码；关键模型、调用点与原生载荷组装交叉核对，
含控制流警告的 ViewModel 另以 fallback 指令输出核对构造调用。

业务 DEX SHA-256 为
`725b9c143aeb94d64117ed1ef9a6e51589b356dc59c8110b4d2d9b4a8e95fa4d`。
其中已恢复以下关系（行号对应本机此次反编译输出，非原始源码行号）：

| 位置 | 直接观察 |
| --- | --- |
| `com/minij/app/model/s.java:1415`，`operationMapProcess()` | 读取 App 的 `userDeviceModeStatsList`，构造字符串映射 `userDeviceModeStatsId`、`value`、`code`；普通参数的 `0` 不会被当作空值丢弃 |
| `com/minij/app/ui/device/ProgramActivity.java:1460` | “点击运行”路径把上述列表包装为 `Optional`，与所选程序及 `activate` 一起传入 ViewModel |
| `com/minij/app/models/DeviceEvent.java:2885` | `DeviceOperateV2` 的参数类型为 `Optional<List<Map<String,String>>>` |
| `com/minij/app/ui/device/wash/x.java:2494–2530`、`:2415–2422` | 烘干开关修改本地参数模型、更新 App 缓存列表，再通过协程调用参数设置包装器 `j2` |
| `com/minij/app/viewmodel/b.java:8227`，fallback 输出 `:14694` | 参数设置创建 `DeviceEvent.StatsSetup`，区别于运行面板的 `SwitchUserStats` |
| `libbloc.so:0x49e7fc–0x49e81c` | 参数设置路径构造 `device/deviceStatsSetup` 的 POST，载荷包含 `deviceId` 与嵌套 `activateParam`；嵌套程序 ID、列表键分别见 `0x49e8e8`、`0x49e9a8` |

启动列表的单项结构已经有业务代码证据，可用以下合成数据表达；不是实际发出的请求：

```json
{
  "userDeviceModeStatsId": "synthetic-parameter",
  "value": "0",
  "code": "dryingCompoundOption"
}
```

`value` 为字符串；此处的 `0` 仅用来示意前文 V6-XNB 选项，不定义跨型号常量。
参数项 ID 来自所选程序的元数据，不是设备 ID 或程序 ID。
`operationMapProcess()` 还对 `dryAggregation` 做子参数展开，并跳过该聚合分支中的 `255`；
不能将其推广为所有参数的过滤规则或完整参数依赖模型。

目前区分出三条路径：

| 路径 | App 代码／请求结构 | 已知限制 |
| --- | --- | --- |
| 程序详情参数设置 | `StatsSetup` → `device/deviceStatsSetup`，`deviceId` + `activateParam`（程序 ID 与参数列表） | 修改烘干选项并非只有本地草稿；持久化语义尚未实测 |
| 启动／继续 | `DeviceOperate` 或 `DeviceOperateV2` → 已有 `deviceOperate` 路径，启动参数含列表 | 列表可非空；服务端是否写回保存设置仍未知 |
| 运行面板单参数设置 | `SwitchUserStats` → 既有 `device/v2/workingUserStatsSetup` | 当前 HA 参数选择使用此路径；不能据接口名字断定永久或临时 |

因此不应把“App 详情页修改烘干”和“运行中叠加烘干”当成同一操作。
**恢复了参数字段，不等于已经证明不改默认值的一次性覆盖。**
上述离线代码取证回合没有登录、加载真实设备详情或发出控制请求，
亦未将 DEX、反编译代码或原始内存提交到仓库。后续授权的云端参数验证见下节。

### 离线复现：由原生核心生成 HTTP effect

在独立断网模拟器中运行维护者编写的 Java 测试程序，通过反射直接加载上述内存 DEX 的
`DeviceEvent`、`Event.Device` 和 `Requests`，调用其真实 bincode 序列化／反序列化。
随后调用 APK 自带 `BlocKt.processEvent` 与同一 `libbloc.so`，读取返回的 HTTP effect。
没有调用 ViewModel 的 HTTP 执行分支，也没有执行 App 的网络发送函数。

输入全部使用 `synthetic-device`、`synthetic-program`、`synthetic-parameter`；
参数映射由测试程序按前述业务代码结构构造，不是从真实设备页面点击产生。
因此这是**合成输入的受控运行复现**，不是 App 界面完整操作或真实服务端验收。
五个独立进程均正常退出，输出如下：

| 合成事件 | 原生核心返回的 POST 路径 | 列表内容 |
| --- | --- | --- |
| `DeviceOperateV2` / activate，空列表 | `/api/device/v2/deviceOperate` | `[]` |
| `DeviceOperateV2` / activate，value `"0"` | `/api/device/v2/deviceOperate` | 包含 `code`、`userDeviceModeStatsId`、字符串 `value` 的单项 |
| `DeviceOperateV2` / activate，value `"2"` | `/api/device/v2/deviceOperate` | 同一结构，value 为 `"2"` |
| `StatsSetup`，value `"0"` | `/api/device/deviceStatsSetup` | 同一结构，value 为 `"0"` |
| `StatsSetup`，value `"2"` | `/api/device/deviceStatsSetup` | 同一结构，value 为 `"2"` |

启动 effect 的 body 包含 `deviceId`、`bucketCode: ""`、`operateType: "activate"` 和
`activateParam`；设置 effect 只包含 `deviceId` 与 `activateParam`。
两者的 `activateParam` 都包含 `userDeviceModeId` 与 `userDeviceModeStatsSimpleList`。
值 `"0"` 确实保留在输出中，未被序列化为缺省或空列表。

没有把 effect 发到 URL，没有注入账号或读取账号存储；HTTP dispatch 次数为 0。
这补齐了客户端请求生成证据，**仍不证明服务端接受、持久化或仅覆盖本次**。
输出与校验仅保留在忽略目录 `analysis/android-re/probe/`，公开说明不包含任何真实标识。

## 所有者授权的待机参数对照

所有者明确允许：V6-XNB 未运行时，仅修改标准程序的烘干参数、回读并恢复原值；
不唤醒、不启动洗涤，若设备正在运行则停止验证。
本轮使用已有会话进行直接云端请求，没有登录新模拟器或发送短信。

只读预检确认设备 `resting`、标准程序唯一、烘干当前值为 `0（无烘干）`，
且该程序的元数据声明 `2（即穿）`。每次参数请求前重新核对设备状态和参数身份。

| 步骤 | 请求／观察 | 证据含义 |
| --- | --- | --- |
| 临时设置 | `device/deviceStatsSetup`，仅提供烘干项 `"2"`；云端接受 | 不等于已保存或物理生效 |
| 独立回读 | `getUserDeviceMode` 三次读取该项，均为 `0`；设备仍 `resting` | 短时间观察窗口内未看到保存参数变成 `2` |
| 恢复 | 同路径写回原值 `"0"`，云端接受；再次读取为 `0` | 本轮结束时原值已确认，未留下更改值 |
| 同原值响应核对 | 保持原值 `"0"` 再调用一次，返回 `data` 为整数 `29`；再次读取仍为 `0` | 确认该接口有数值响应，不据此猜测单位 |

这轮共发送三次详情参数 POST（临时值、恢复原值、同原值响应核对），没有 `power_on`、
`activate`、`pause` 或 `power_off` 请求；设备状态读取全程为 `resting`。
这不是现场观察，不能据此宣称面板、运行中的烘干或实际洗涤效果通过。

反编译的 ViewModel `i2` 在参数请求后读取 `device.current.predictExecTime`，
更新程序时长显示（`viewmodel/b.java:8258–8295`）；与本轮接口返回数值一致，
支持其参与详情页的程序时长预估。**不能仅凭 `StatsSetup` 名称把它当作已经验证的保存／清除接口。**

仍不能排除待机状态、只传单项、时序或其他服务端条件影响结果；
本轮也没有测试 `workingUserStatsSetup` 的持久化行为。
因此不把“未看到改变”推广为该接口永不保存，更不把它当作启动时单次覆盖的证明。
脱敏结果保留在本机忽略目录；公开记录没有账号、设备、程序或参数项的真实标识。

## 下一步

1. 只读加载目标程序后断网，分别修改烘干和其他参数，核对是否生成单参数保存请求，
   或仅改变待提交列表；离线启动后停止 App，避免未完成指令在恢复联网后发出。
2. 已从业务代码恢复非空列表结构，并由真实原生核心离线生成五种合成载荷；
   已完成授权的待机参数回读与原值确认，但没有观察到持久化改变。
   后续在所有者正常洗涤、有现场授权时核对启动时直接携带参数的实际效果，
   并独立读取运行参数与保存参数；不为研究额外启动洗涤。
3. 请 U10 Pro 报告者只分享烘干项的 `code/name/type/value` 与选项 `label/value`，
   去掉所有 `id` 和账号字段；无需原始诊断，也无需额外启动洗涤。
4. 在语义确认后再设计“只洗／洗烘”组合操作；显式选择设备提供的选项，
   处理回读不一致和中途失败，禁止用空参数列表暗示关闭烘干。

当前没有经过验证的单次覆盖实现，不新增猜测载荷、不自动改回设置、不重试启动。
现有[控制指南](local-controls-0.4.md)与[通知蓝图](automations.md)继续适用。

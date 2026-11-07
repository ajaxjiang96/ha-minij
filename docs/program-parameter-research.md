# 程序保存参数与启动覆盖研究

更新于 2026-11-07。对应 [Issue #29](https://github.com/ajaxjiang96/ha-minij/issues/29)。
本记录区分社区客户端反馈、V6-XNB 历史读取和 Android App 静态路径；不改变集成控制行为。

## 社区反馈：U10 Pro

报告设备为 U10 Pro 内裤洗烘一体机，云端型号 `minij.pants.x1`，带自动投放。
报告者基于本项目协议编写了独立客户端，接入自己的 AI 助手，未使用本 HA 集成。
其反馈短信登录、设备列表、状态/程序查询、启动、停止、启动后叠加烘干和通知查询可用。
这属于社区对云端协议的使用反馈，不能据此标记本 HA 集成已完成 U10 Pro 验收。

报告者观察到：App 使用一次“日常洗＋烘干”后，仅指定日常洗启动，仍沿用先前的烘干设置；
启动后写入 `dryingCompoundOption=2` 可叠加即穿，烘干阶段暂停被服务端拒绝。
这些观察尚未由维护者在 U10 Pro 上复现，不推广为其他型号的枚举或阶段规则。

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
  并非无条件构造空数组；映射元素的具体业务键仍须从界面调用方或离线生成请求确认。

因此已确认原生启动组装路径支持由调用方提供列表，尚未确认哪些洗衣机界面会填入它、
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

## 下一步

1. 只读加载目标程序后断网，分别修改烘干和其他参数，核对是否生成单参数保存请求，
   或仅改变待提交列表；离线启动后停止 App，避免未完成指令在恢复联网后发出。
2. 从确切请求恢复非空列表结构；即使服务端接受，也需分别核对运行参数与再次读取的保存参数，
   才能判断是否影响默认值。真实控制验证另行获得所有者授权。
3. 请 U10 Pro 报告者只分享烘干项的 `code/name/type/value` 与选项 `label/value`，
   去掉所有 `id` 和账号字段；无需原始诊断，也无需额外启动洗涤。
4. 在语义确认后再设计“只洗／洗烘”组合操作；显式选择设备提供的选项，
   处理回读不一致和中途失败，禁止用空参数列表暗示关闭烘干。

当前没有经过验证的单次覆盖实现，不新增猜测载荷、不自动改回设置、不重试启动。
现有[控制指南](local-controls-0.4.md)与[通知蓝图](automations.md)继续适用。

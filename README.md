# 小吉 MiniJ · Home Assistant 集成

<img src="custom_components/minij/brand/icon.png" alt="小吉 App 图标" width="80">

非官方的小吉云端状态监测集成。目前已在 **V6-XNB 壁挂洗烘机**
（内部型号 `minij.washer.x68`）上验证登录和状态读取。

这是限定机型的**云端状态监测集成**，稳定版范围限定于本文列出的监测功能。
实际已发布版本以 GitHub Releases 为准。仓库文档优先使用简体中文；
HA 界面跟随用户的语言设置，提供简体中文和英文。

## 已支持的功能

| 实体 | 内容 |
| --- | --- |
| 状态 | 设备上报的状态别名及原始状态文字 |
| 设备上报程序 | 控制器上报的程序名称 |
| 设备上报进程 | 控制器上报的阶段名称 |
| 童锁已开启 | 明确的 open/close 状态 |
| 云端控制已授权 | 明确的云端控制授权状态 |

每 60 秒共享一次设备列表请求。成功读取时同步云端设备名称、型号和固件，
保留 HA 自定义名称、区域及既有标识。未知开关值显示为未知；云端刷新失败或设备解绑时，
实体显示为不可用。更换凭据不会改变设备和实体的唯一标识。

当前设备基线：Wi-Fi `1.0253`，设备固件 `0 0003 1 0000`。
已观察到 `resting`、`working` 和 `device_exception`。其他型号和固件尚待验证。

## 安装

推荐按照 [HACS 自定义仓库指南](docs/hacs-installation.md)安装和更新。
首个监测稳定版 [v0.1.1](https://github.com/ajaxjiang96/ha-minij/releases/tag/v0.1.1) 已发布；
后续版本请查看 [GitHub Releases](https://github.com/ajaxjiang96/ha-minij/releases)。
以下是手动安装方式：

需要 **Home Assistant 2026.10.4 或更新版本**。

1. 将仓库中的 `custom_components/minij` 完整复制到 HA 配置目录的
   `custom_components/` 下，包含 `translations/` 子目录。
   也可执行 `python scripts/package_integration.py`，将生成的 ZIP 解压到 HA 配置目录。
2. 重启 Home Assistant。
3. 打开 **设置 → 设备与服务 → 添加集成 → MiniJ**。
4. 选择**手机验证码（实验功能）**或**已有会话令牌（高级）**。
5. 手机号使用已有小吉账号的 11 位中国大陆号码，不带 `+86`。
   提交号码才会发送一条短信，再输入短信验证码即可。

验证码和令牌使用遮挡输入框。配置中只保存验证后的会话令牌，不保存手机号或验证码。
账号与设备访问检查失败时，“重试”只重复读取，不会再次发送短信或兑换验证码。
更换号码或重新获取短信需取消后重新开始，请避免重复请求。

已有条目可从 **⋮ → 重新配置** 更新认证，不需要删除设备；重新认证必须使用原账号。
账号所有者反馈短信流程可用，且本次登录后手机 App 仍能直接查看设备；
也已观察到 HA 启动后自动恢复，无需短信。长期有效期、其他会话轮换情形、
验证码冷却和额外验证仍未完整确认。遇到不支持的验证步骤，可使用自己的 App 会话令牌。
详见[登录验证指南](docs/sms-acceptance.md)和[认证证据](docs/authentication.md)。

源码：[ajaxjiang96/ha-minij](https://github.com/ajaxjiang96/ha-minij)。
HACS 自定义仓库无需等待默认列表收录。
稳定版范围和限制见[0.1.1 发布说明](docs/releases/0.1.1.md)与[支持政策](docs/support.md)。

## 当前限制

- **运行后回到空闲，不等于已确认正常完成。** 取消、停止等情况尚未区分；
  当前不提供完成事件或默认完成通知。
- 空闲时的程序和进程可能保留先前值，不能仅凭“主洗”“脱水”等文字判断仍在运行。
- 暂不提供剩余时间，单位及倒计时语义尚未确认。
- 可用性表示云端读取和设备绑定情况，尚不能代表设备的物理联网状态。
- `device_exception` 本身不能说明具体故障原因。
- 未假设令牌有效期或刷新接口；状态读取收到 HTTP 401/403 时进入重新认证。
- 当前不提供启停、程序选择、固件管理、局域网控制或 MQTT。

这些未提供的能力不属于首个监测版承诺。无需为了发布额外运行洗涤；
有正常使用机会时，再补充验证即可。

## 诊断与支持

MiniJ 条目的 **下载诊断信息** 提供已缓存的型号、固件和白名单状态字段，
不会额外轮询、发送短信或操作设备。MiniJ 数据部分不包含凭据或小吉标识符；
HA 会在外围添加系统信息，分享前请检查。

- [常见问题与更新方法](docs/troubleshooting.md)
- [安全的状态自动化示例](docs/automations.md)
- [支持范围与反馈政策](docs/support.md)
- [日常洗涤观察指南](docs/cycle-validation.md)
- [完整集成路线图](docs/roadmap.md)：可靠监测、周期自动化、控制与多型号扩展
- [首个稳定版验收记录](docs/stable-release-checklist.md)
- [测试结果与证据边界](docs/validation.md)
- [开源基础状态](docs/foundation.md)
- [开发与贡献](CONTRIBUTING.md)

技术调查记录：[总览](docs/investigation.md)、[原生 HTTP](docs/native-http.md)、
[公开网页协议](docs/web-protocol.md)、[Android 运行证据](docs/runtime.md)、
[REA 工具](docs/rea-setup.md)。这些历史研究记录暂保留英文，面向用户的指南优先维护简体中文。

项目原创代码采用 [MIT 许可证](LICENSE)。用户提供的小吉图标和产品名称用于标识支持的产品，
不作为项目原创作品重新授权。本项目与小吉官方无关联。

# 通过 HACS 安装和更新

需要已安装 HACS、Home Assistant 2026.10.4+，以及绑定设备的小吉账号。
仓库是非官方监测预览版，目前通过**自定义仓库**安装，不属于默认列表。

## 添加仓库

1. 打开 HA 侧栏的 **HACS**。
2. 右上角 **⋮ → 自定义仓库**，仓库填写
   `https://github.com/ajaxjiang96/ha-minij`，类型选择 **集成 / Integration**，添加。
3. 搜索 **MiniJ**，打开仓库详情并选择下载。
4. 已发布测试版时，在下载/重新下载界面启用**显示测试版 / beta**，
   选择对应的 `v0.1.1b1` 等版本。不同 HACS 版本的文字可能略有不同。
   如果尚未发布版本，HACS 可读取默认分支；不要把计划版本误认为已发布。
5. 重启 HA，进入 **设置 → 设备与服务 → 添加集成 → MiniJ**，按提示登录。

[在 HA 中打开本仓库](https://my.home-assistant.io/redirect/hacs_repository/?owner=ajaxjiang96&repository=ha-minij&category=integration)
需要你自己的 HA 地址和已安装的 HACS；本链接不会替你登录小吉。

## 已有手动安装

首个测试版使用 `0.1.1b1`，高于先前未发布的开发包 `0.1.0`，
避免包管理器将新测试版视为降级；配置结构不变，无需迁移或重新建条目。

更新前备份 HA。让 HACS 下载到相同的 `custom_components/minij` 位置，
保留现有集成条目，不重新创建账号、设备或实体，重启后确认原来的五个实体仍在。
不要在 HACS 和手动文件之间反复覆盖不同版本。

若菜单空白或仍显示旧说明，重启 HA 后按 **Cmd+Shift+R**（Windows/Linux 为
**Ctrl+Shift+R**）刷新，并检查翻译文件完整。

## 更新、回退与卸载

- 在 HACS 仓库菜单更新信息后，下载/重新下载需要的版本并重启 HA。
  仅更新仓库信息不会替换本地组件。
- 回退使用 HACS 的版本选择器，或用更新前备份恢复；保留条目及实体标识。
  尚无公开稳定版时，不假设存在可回退的稳定版本。
- 完全卸载时，先在“设置 → 设备与服务”删除 MiniJ 条目，再从 HACS 移除组件并重启。

## 独立安装验收

记录 HACS/HA 版本、安装的版本标签、公开型号与固件，确认：

- 下载和重启后能打开中文登录流程，不依赖 APK 或模拟器；
- 自己的账号可登录并看到绑定设备的五个实体；
- 既有用户更新后，原实体 ID、名称、区域和自动化不变；
- 正常重启后无需重新发送验证码即可恢复，若失败只记录提示；
- 可下载诊断，分享前检查 HA 外围系统元数据并删除隐私。

不必为验收额外洗涤，不触发固件更新或设备控制。
尚未完成独立真实 HACS 安装时，CI 和 ZIP 测试只能证明各自覆盖的部分。

依据：[HACS 仓库布局与发布](https://www.hacs.xyz/docs/publish/integration/)、
[版本规则](https://www.hacs.xyz/docs/publish/start/)、
[下载和更新操作](https://www.hacs.xyz/docs/use/repositories/dashboard/)。

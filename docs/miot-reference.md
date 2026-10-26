# MIoT v17 规格与 HA 实现参考

核对日期：2026-10-26。用途：完善 V6-XNB 的能力清单与 HA 实体设计，
不把其他型号/后端的枚举、单位或控制指令当成本机已支持。

## 先区分目标和协议

所有者确认这台 V6-XNB 只能在小吉 App 使用，当前小吉云设备标识为 `minij.washer.x68`。
本次参考对象是米家侧 `minij.washer.v17`。两个标识没有建立协议等价关系，
不能因为都是小吉壁挂洗烘机，就套用 MIoT 的服务/属性编号或改接小米账号。
当前集成继续使用已验证的小吉云接口；米家型号的直接接入应另行使用真实米家设备验证。

资料来源：用户提供的 [v17 展示页面](https://home.miot-spec.com/spec/minij.washer.v17)，
以及已实际获取的 [MIoT 原始实例 JSON](https://miot-spec.org/miot-spec-v2/instance?type=urn%3Amiot-spec-v2%3Adevice%3Awasher%3A0000A01F%3Aminij-v17%3A1)。
JSON SHA-256：`0c1866db5c784a2b7f4c2e17336f3ce85e941e9000e04727f5f8ed5d61e37cd9`。
原始下载仅作本地研究，不将完整第三方规格或实现代码复制到组件。

## 可借鉴的能力结构

下表编号均仅指 v17 的 `siid.piid`、动作或事件，不是 x68 的可调用地址。

| v17 参考 | 可以借鉴的 HA 设计 | x68 仍需取得的证据 |
| --- | --- | --- |
| `2.2 status` 区分暂停、完成等状态；`2` 服务有独立 `wash-end` 事件 | 状态传感器与完成事件分开 | 暂停/取消别名；完成已通过小吉官方消息独立确认 |
| `2.3 mode` 为运行模式，`6.1 cycle` 才是程序选择 | 不将运行模式与洗涤程序混为一个实体 | 程序代码/名称、允许值与可写载荷 |
| `4.1 timetotal`、`4.3 timeremain` 明确为 minutes | duration 传感器；预约另用 hours | 剩余分钟已有 App/API 对照；总时长、暂停/烘干边界仍需对照 |
| `5.6 lock` 与 `5.8 childlock` 分开 | 门锁只读状态、童锁能力分别判断 | 门锁字段和童锁是否可远程写，不能复用同一“锁” |
| `2` 服务提供开始/暂停动作 | 明确动作与状态前提，验证后选按钮/动作 | 小吉云请求、授权、拒绝和真实回读；MIoT 动作编号不能直接调用 |
| `6` 服务包含温度、转速、烘干、漂洗等设置 | 根据真实值表决定 select/number | 数字是档位还是物理量；不能将范围直接标成 °C 或 rpm |
| 多个不同服务都有 fault 属性 | 以完整服务/属性身份定位，不按短名合并 | v17 的不同范围也不等于 x68 故障码表 |
| `7` 服务有用水/用电原值，原始单位未明确 | 先保留含义未知，再考虑统计实体 | 小吉云是否返回、累计/单次含义及单位；不先赋 L/kWh |

这份原始 JSON 中，`2.3 mode` 的 `0` 为 `Off`，展示页却显示 `Auto`；
因此查到差异时优先回到原始实例，再由设备验证，不直接复制展示文字。
v17 的时间范围 `0..500`、温度/转速档位范围也不能拿来限定 x68 的上报值。

## 已学习的两个 HA 项目

### Xiaomi 官方 ha_xiaomi_home

核对提交 `75b3acb6325a3a8d295688b13904737d6738a6a5`。
[miot_device.py 的 spec_transform](https://github.com/XiaoMi/ha_xiaomi_home/blob/75b3acb6325a3a8d295688b13904737d6738a6a5/custom_components/xiaomi_home/miot/miot_device.py#L672)
按权限、格式、值表和范围选择实体：可写布尔、可写枚举、可写范围分别映射到
switch/select/number，只读属性进入传感器，事件独立处理，无参数动作可用 button。
设备/服务转换前还检查所需属性、动作及访问权限。

借鉴结论：**先证实设备能力和读写权限，再暴露相应实体**。
这些转换规则消费 MIoT specs；x68 的小吉云没有自动获得同一份可写能力描述。
不引入它的 OAuth、MIPS 或 LAN 栈来替代现有已工作的接口。

### 社区 hass-xiaomi-miot

核对提交 `f78158257e19a21902adaf6bcc8440c3ba172a91`。
[core/converters.py](https://github.com/al-one/hass-xiaomi-miot/blob/f78158257e19a21902adaf6bcc8440c3ba172a91/custom_components/xiaomi_miot/core/converters.py#L99)
将属性值/描述转换与动作编码分开；映射身份包含服务和属性/动作编号。
[device_customizes.py](https://github.com/al-one/hass-xiaomi-miot/blob/f78158257e19a21902adaf6bcc8440c3ba172a91/custom_components/xiaomi_miot/core/device_customizes.py#L1500)
还针对 `minij.washer.v20` 单独调整运行/非运行状态描述；这不是 v17 或 x68 的枚举证据。

借鉴结论：**保留原始值、按型号收敛差异、把显示转换与写指令分开**。
不复制 v20 状态名单到本机，也不为尚无第二个已验证型号预建通用家电框架。

两个项目的许可证分别见
[官方项目 LICENSE.md](https://github.com/XiaoMi/ha_xiaomi_home/blob/75b3acb6325a3a8d295688b13904737d6738a6a5/LICENSE.md) 和
[社区项目 LICENSE](https://github.com/al-one/hass-xiaomi-miot/blob/f78158257e19a21902adaf6bcc8440c3ba172a91/LICENSE)。
本次仅参考设计和链接出处，组件保留原创实现，没有复制源代码或新增依赖。

## 对接下来的实现有什么影响

1. 建立 x68 自己的能力表：字段、原始值、单位、读写权限、来源与验证状态。
   读到童锁状态不等于已经证实可写，界面出现开关也不等于命令已执行。
2. 优先研究已有真实状态字段对应的童锁控制路径，再研究开始/暂停和程序参数。
   此阶段先做只读协议追踪；真实指令验证仍由所有者选定设备状态和操作后进行。
3. 每条控制取得实际小吉云载荷、前提及回读证据后再加实体；
   不写 MIoT 编号、不假设整数枚举相同、不默认允许全部参数。
4. 保留已有完成事件与运行状态分离的设计；暂停/取消、总时间和故障继续按本机证据补齐。

本文件不代表 v17、米家登录或上述候选控制已在本集成支持。

# 参与贡献

文档、Issue 和 PR 优先使用简体中文。协议字段、代码标识符、命令及 Home Assistant
要求的英文源文案保留原样；界面同时维护简体中文翻译，不强制覆盖用户的语言选择。

每项变更应在已验证机型上形成完整可用的功能。新增字段或控制能力时，说明型号、固件、
预期行为和支持结论的证据。未知值应保留未知，不根据名称或数字猜测含义。

## 开发

使用 Python 3.14.2 或更新版本，并创建独立环境：

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check custom_components tests scripts
.venv/bin/python -m ruff format --check custom_components tests scripts
.venv/bin/python -m pytest -q
.venv/bin/python scripts/package_integration.py
```

自动化测试使用本地 HTTP 服务和合成账号、设备记录，不需要小吉账号，
不得发送验证码或操作真实设备。Linux CI 分别测试声明的最低及当前发布版 HA。
测试进程必须退出 0 才算通过，不能只看断言数量。

## 证据与隐私

原始研究材料保留在被忽略的 `analysis/` 中。公开样例使用 `test-account`、
`washer-test-device` 等合成标识和相对时间，删除令牌、验证码、手机号、序列号、
账号和设备 ID、Wi-Fi 信息、IP、姓名及可识别的图片或链接。
提交前检查完整差异和暂存文件列表，不提交 APK、厂商反编译代码、原始抓包或本地工具环境。

真实账号验证与自动化测试分开。发送短信、退出登录、撤销令牌、操作设备或安装固件时，
需要账号或设备所有者参与。凭据不能进入测试、截图、日志、Issue 或 PR。

## 提交 PR

先描述用户遇到的问题和变更后的行为，再说明验证结果与仍未知的部分。
凭据、名称或设备状态变化不能改变已有实体的唯一标识。
其他型号需要真实设备证据及回归样例，安装成功不等于全部能力已验证。

可在已知限制下推进监测预览版，无需为了交付强行等待另一轮洗涤。
但不能将“运行 → 空闲”直接标记为正常完成，也不能虚构物理离线、剩余时间或令牌有效期。

普通问题和型号反馈请使用 Issue 模板。若凭据意外泄露，先在账号提供方撤销，
再提交去除敏感信息的报告，勿将凭据粘贴到公开 Issue。

测试版标签、附件和发布边界见[维护者发布流程](docs/releasing.md)。
发布前要验证实际 ZIP，而不仅是源码目录；CI 的隔离安装烟测覆盖包内组件加载。

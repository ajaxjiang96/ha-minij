# 开源基础状态

记录日期：2026-10-26。公开仓库为
[ajaxjiang96/ha-minij](https://github.com/ajaxjiang96/ha-minij)，由所有者明确要求创建。

## 已完成

- Git、MIT 许可证、原创集成代码、合成测试、贡献/排障说明和问题模板。
- 真实仓库/维护者链接、HACS 元数据、用户提供且原样复制的小吉图标。
- 只包含运行文件的手动安装 ZIP。
- 固定提交的 GitHub Actions：最低/当前 HA、Ruff、hassfest、HACS 和打包校验。
- Dependabot 更新；翻译与主要文档优先支持简体中文，保留英文界面资源。
- APK、原始日志、凭据、抓包、本地工具和环境均被忽略；公开差异做敏感数据检查。

## 发布与合并

公开仓库在代理稳定后通过用户已登录的 GitHub 浏览器创建。
此前 EOF / `ERR_CONNECTION_CLOSED` 不能证明凭据无效。
源码推送使用 SSH，并显式禁止密码提示及 Keychain。

[基础 PR #1](https://github.com/ajaxjiang96/ha-minij/pull/1) 由用户合并为 `502f89d`，
检查通过，Codex 对 `810a5ca` 审查无发现。
[短信 PR #4](https://github.com/ajaxjiang96/ha-minij/pull/4) 已合并为 `128bfda`；
随后主分支还合并了 Actions 依赖更新。
[诊断 PR #5](https://github.com/ajaxjiang96/ha-minij/pull/5) 提供诊断和日常周期观察能力。
PR 检查通过与实际合并是不同状态，发布前重新查询。

首个测试版 [v0.1.1b1](https://github.com/ajaxjiang96/ha-minij/releases/tag/v0.1.1b1)
已发布，标签对应合并提交 `489c35d`，验证和发布任务全部通过。已实际下载核对
ZIP 的 SHA-256 和 14 个包内文件，均与标签一致。所有者确认已由 HACS 安装；
这不等于 HACS 默认列表收录。

## Linux 与凭据提示

代理恢复后，官方 Python 镜像经 manifest、config、压缩层和解压层摘要核验后导入本地容器。
基础测试在 Linux ARM64 完整退出 0，后续 Linux CI 也通过，详见[验证记录](validation.md)。

第一次 Docker 拉取触发已有凭据助手并被取消；没有输入密码。
后续使用只含 `{}` 的独立 Docker 配置，不含凭据助手；没有修改用户全局 Docker 配置或 Keychain。
macOS 解释器收尾故障未被掩盖，Linux 结果独立判断。

## 预览版与稳定版

监测预览版可在写明限制后继续推进，不需要再等待一次正常完成。
稳定版承诺仍受会话持久性、状态含义和独立安装证据限制。
没有证据的完成、离线、倒计时或刷新机制不添加。发布前对确切提交检查 CI 和支持范围。

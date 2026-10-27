# 维护者版本发布流程

当前发布准备为 `0.4.0b5`，标签应为 `v0.4.0b5`，保持测试版、非 latest。
既有稳定版为 `0.1.1`，测试版发布不自动替换稳定渠道。
更新 manifest 只是准备工作，PR 合并不会自动发布；推送匹配标签才触发发布工作流。

## 发布前

1. 审查并合并版本准备 PR，确认最低/当前 HA、hassfest 和 HACS 全绿。
2. 确认 `custom_components/minij/manifest.json` 的版本，
   以及 `docs/releases/<版本>.md` 的中文说明和已知限制。
3. 标签指向已合入 `main` 的确切提交，而不是未合并分支。
4. 通过手动安装或 HACS 自定义仓库收集反馈；没有完成的真实验收不能写成已完成。

## 发布动作

在已更新到目标主分支提交的检出目录中：

```sh
git tag v0.4.0b5 <已审查的完整提交哈希>
git push origin v0.4.0b5
```

这是实际发布动作，应在决定公开该版本时执行。
不要用占位符直接执行，不要移动已发布标签或覆盖旧附件。

标签触发 `.github/workflows/release.yml`：先复用完整验证，全部成功后才进入发布任务。
发布任务核对提交属于主分支历史、标签与 manifest 一致、版本属于 X.Y.Z 稳定版或 X.Y.ZbN 测试版、
中文发布说明存在，再生成 ZIP 和 `SHA256SUMS`。
稳定版显式设置 prerelease=false、latest=true；测试版保持 prerelease=true、latest=false。
版本分类及标志通过回归测试，避免将测试版自动提升为稳定版。
仅发布任务具有 `contents: write`；检出不保留凭据，不使用维护者个人令牌或本机 Keychain。

如果验证或版本检查失败，不会创建 Release。重试前先确认失败原因及是否已有同名 Release；
不通过移动标签掩盖差异，需要修改源码时使用新的版本编号。

## 两种下载方式

HACS 默认读取仓库的 `custom_components/minij/`，用 Release 标签选择版本，
无需额外的 `zip_release` 配置或第二种 ZIP 布局。
附带的 `ha-minij-<版本>.zip` 面向手动安装，保留 `custom_components/minij/` 路径，
直接解压到 HA 配置目录；不要把它当成 HACS 专用根目录压缩包。

本地运行 `python scripts/package_integration.py` 可生成同样布局的安装包。
测试会将包解压到源码树之外，只使用包内组件启动真实 HA、加载默认活动实体并卸载。
这是无真实小吉账号的安装烟测；真实 HACS 下载、更新和重启仍按
[独立安装指南](hacs-installation.md)验收。

## 发布后

确认 Release 的稳定/预发布标志与版本一致、标签/提交正确，ZIP 与校验文件可下载，
并在 HACS 版本选择中能找到对应版本。再记录真实安装结果，避免把 CI 通过说成 HACS 前端验收。

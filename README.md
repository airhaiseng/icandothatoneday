# icandothatoneday · 静态看板发布包

这是把现有 `daily_review` 看板发布到 `airhaiseng/icandothatoneday` 的发布包。

## 先说结论：不需要 VitePress / MkDocs

现有 `dashboard.html` 已经是**自包含静态网页**，包含：

- 总览 / 选股 / 策略定制 / 我的操作台
- K 线、MA、RSI、权益曲线、回撤、交易记录
- 数据已嵌入 HTML，不依赖 Node、VitePress、MkDocs 或后端

Markdown → 网页只能得到只读报告，会丢掉选股、参数调整、回测和自选股。直接用现有静态页即可。

## 已选择：Public + GitHub Pages

你已选择把仓库改成 **Public**，使用 GitHub Pages 免费托管。

- 仓库地址：`https://github.com/airhaiseng/icandothatoneday`
- 站点地址：`https://airhaiseng.github.io/icandothatoneday/`
- 注意：**仓库和站点都会公开**，策略、收益、回撤、交易记录都可见。
- 不要放券商账号、API key、身份证、真实持仓截图。

## 发布步骤

1. 仓库 `airhaiseng/icandothatoneday` 已是 **Public**（已确认）；当前还是空的，直接进入上传。
2. 把本目录的内容上传到仓库根目录（GitHub 网页 “Add file → Upload files”，或 `git push`）。
   - 网页上传若没有带上 `.github` 目录，用 **Add file → Create new file**，文件名填 `.github/workflows/daily.yml`，把本目录里的工作流内容粘贴进去。
3. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
4. 打开 **Actions → Daily review → Run workflow** 手动跑一次。
5. 完成后访问：

   `https://airhaiseng.github.io/icandothatoneday/`

   注意末尾斜杠。

> `airhaiseng` 账号已确认存在；私有仓库 API 返回 404 是正常的。改成 Public 后，Pages 才能在 Free 账户上启用。

## 自动更新

`.github/workflows/daily.yml` 每天 UTC 14:00（北京时间 22:00）运行：

1. `python daily_review/review.py`：拉行情、算三策略、写 Markdown
2. `python daily_review/build_dashboard.py`：生成最新 `dashboard.html`
3. 复制到 `site/`，通过 GitHub Pages 发布

也可以在 Actions 页面点 **Run workflow** 立即更新。GitHub 的定时任务可能延迟几分钟。

## 暂停自动复盘（避免不必要消耗）

**当前发布包状态：已暂停**（`daily_review/state/auto_review.json` 的 `paused: true`）。页面顶部会显示“自动复盘 已暂停”。

本地暂停/恢复：

- 双击 `daily_review/pause_auto_review.cmd`：写状态并禁用 Windows 任务（如果有）
- 双击 `daily_review/resume_auto_review.cmd`：恢复
- `run_review.ps1` 在暂停时直接退出，不跑 Python、不拉行情
- 只想跑一次：`run_review.ps1 -Force`

GitHub Actions 暂停（二选一）：

1. 仓库 **Settings → Secrets and variables → Actions → Variables** 添加：
   `AUTO_REVIEW_PAUSED = true`
   工作流的 `if` 会跳过构建；恢复时改成 `false` 或删除变量。
2. 或打开 **Actions → Daily review**，右上角 **Disable workflow**。

> 暂停后站点不会更新，页面保留最后一次发布的内容；本地页面会显示“已暂停”。DSH 内置 22:00 定时已在本地移除，不会调用模型、不消耗 token。

## 隐私提醒

GitHub Pages（免费方案）要求仓库 Public，**站点和代码都会公开**：

- 策略参数、收益、回撤、交易记录会公开
- 看板里的“备注”只存在浏览器 localStorage，不会上传
- 不要在这个仓库里放券商账号、API key、身份证、真实持仓截图

如果不想公开：GitHub Pages 私有仓库需要付费计划；可以改用 Cloudflare Pages / Netlify（私有仓库 + 免费额度），或只在本机打开 `dashboard.html`。

## 本地预览

`site/index.html` 可以直接双击打开；它和仓库发布的是同一份页面。

## 目录

```
.github/workflows/daily.yml   # 每日构建 + Pages 部署
daily_review/
  review.py                   # 行情 + 三策略 + Markdown
  build_dashboard.py          # 生成自包含 dashboard.html
  dashboard_template.html     # 页面模板（改这里）
  config.json                 # 策略参数
  data/                       # 行情缓存（断网回退）
  state/auto_review.json      # 暂停状态（当前 paused: true）
  pause_auto_review.cmd       # 暂停
  resume_auto_review.cmd      # 恢复
  control_auto_review.ps1     # 状态/任务开关的实际脚本
site/
  index.html                  # 首次发布用的页面
  reports/latest.md           # 报告原文
  .nojekyll
```

## 没有 Git?

本机当前没有 `git` / `gh`，也没有 GitHub 登录信息。`airhaiseng` 账号和 `icandothatoneday` 私有仓库已确认存在，但无法从本机直接推送。最简单的做法：

- 用 GitHub 网页创建仓库并上传本目录；
- 或安装 GitHub Desktop / Git 后再推送；
- 或在有权限的机器上执行 `git init && git add . && git commit && git push`。

不要把 GitHub token 直接发在聊天里；用本机凭据管理器或 GitHub Desktop 登录更安全。

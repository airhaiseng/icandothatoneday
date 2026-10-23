# icandothatoneday · 静态看板发布包

这是把现有 `daily_review` 看板发布到 `airhaiseng/icandothatoneday` 的发布包。

## 本次同步（2026-10-23 20:55）

本次把「固定回测窗口」的修复同步进了发布包。仓库现有版本停留在 10-19，落后不止一轮。

**仓库里还没有、需要新增上传的文件（5 个）**：

- `daily_review/control_server.py`
- `daily_review/start_control_server.cmd`
- `daily_review/start_control_server.ps1`
- `daily_review/register_us_task.ps1`
- `daily_review/open_dashboard.cmd`

**已有、需要覆盖为新版的文件**：

| 文件 | 变化 |
|---|---|
| `daily_review/review.py` | 回测窗口改为固定起始日；报告增加“回测区间”；`metrics.csv` 增加 `window_start`/`window_end` |
| `daily_review/config.json` | 新增 `start_date` / `warmup_days`；`history_days` 降级为图表长度 |
| `daily_review/build_dashboard.py` | 传入 `start_date`；抓行情不再覆写 `data/` 缓存 |
| `daily_review/dashboard_template.html` | 与本地一致（仓库旧版小约 3 KB） |
| `daily_review/dashboard.html` | 最新快照；CI 每次会重建，可不上传 |
| `site/index.html` | 最新首屏（首次发布用；之后由 Actions 覆盖） |
| `site/reports/latest.md` | 最新报告原文 |

**上传后站点数字会变**：旧口径 A -1.80% / B +16.90% / C -11.82%，新口径 A -6.87% / B -30.91% / C -15.65%。
不是新亏损，而是回测窗口从“近 10 个月（滚动 300 根）”改成“自 2025-01-01 起算”。

上传方法：网页进入仓库 → **Add file → Upload files**，把对应文件拖进去覆盖；新增文件同样走这里（可整个 `daily_review` 文件夹拖入，GitHub 会按文件名覆盖同名文件）。

## 先说结论：不需要 VitePress / MkDocs

现有 `dashboard.html` 已经是**自包含静态网页**，包含：

- 总览 / 选股 / 策略定制 / 我的操作台
- K 线、MA、RSI、权益曲线、回撤、交易记录
- 预置 10 只 A 股 + 6 只美股（AAPL/MSFT/NVDA/TSLA/BABA/JPM）+ 4 个 crypto
- 数据已嵌入 HTML，不依赖 Node、VitePress、MkDocs 或后端

Markdown → 网页只能得到只读报告，会丢掉选股、参数调整、回测和自选股。直接用现有静态页即可。

## 已选择：Public + GitHub Pages

你已选择把仓库改成 **Public**，使用 GitHub Pages 免费托管。

- 仓库地址：`https://github.com/airhaiseng/icandothatoneday`
- 站点地址：`https://airhaiseng.github.io/icandothatoneday/`
- 注意：**仓库和站点都会公开**，策略、收益、回撤、交易记录都可见。
- 不要放券商账号、API key、身份证、真实持仓截图。

## 发布步骤

1. 仓库 `airhaiseng/icandothatoneday` 已是 **Public**；里面是 10-19 的旧版本，按上面“本次同步”覆盖即可。
2. 把本目录的内容上传到仓库根目录（GitHub 网页 “Add file → Upload files”，或 `git push`）。
   - 网页上传若没有带上 `.github` 目录，用 **Add file → Create new file**，文件名填 `.github/workflows/daily.yml`，把本目录里的工作流内容粘贴进去。
3. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
4. 打开 **Actions → Daily review → Run workflow** 手动跑一次。
5. 完成后访问：

   `https://airhaiseng.github.io/icandothatoneday/`

   注意末尾斜杠。

> `airhaiseng` 账号已确认存在；私有仓库 API 返回 404 是正常的。改成 Public 后，Pages 才能在 Free 账户上启用。

## 自动更新

`.github/workflows/daily.yml` 每天运行两次：

- UTC 14:00（北京时间 22:00）：A 股 / crypto 复盘
- UTC 22:00（北京时间次日 06:00）：美股收盘后刷新

每次都会：

1. `python daily_review/review.py`：拉行情、算三策略、写 Markdown
2. `python daily_review/build_dashboard.py`：生成最新 `dashboard.html`
3. 复制到 `site/`，通过 GitHub Pages 发布

也可以在 Actions 页面点 **Run workflow** 立即更新。GitHub 的定时任务可能延迟几分钟。

## 暂停 / 恢复自动复盘

**当前发布包状态：已暂停**（`daily_review/state/auto_review.json` 的 `paused: true`）。页面顶部会显示“自动复盘 已暂停”。

> 注意：**本地暂停不影响 GitHub Actions**。截至 2026-10-23，Actions 仍在每天跑（最近一次 10-23 06:19 成功），
> 用仓库里的旧代码刷新站点。要停掉线上更新，得按下面“GitHub Actions 暂停”设置仓库变量或禁用 workflow。

**界面开关（推荐，本地）**：

1. 双击 `daily_review/start_control_server.cmd`
2. 打开 `http://127.0.0.1:8777/`
3. 进入 **我的操作台 → 自动复盘开关**
4. 点“暂停自动复盘”或“恢复自动复盘”

注意：`file://` 打开或 GitHub Pages 上的按钮是禁用的；静态页没有权限控制本机。必须使用本地 `http://127.0.0.1:8777/`。

命令行方式：

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
  control_server.py           # 本地界面开关 API
  start_control_server.cmd    # 启动 http://127.0.0.1:8777/
  open_dashboard.cmd          # 双击打开本地仪表盘
  pause_auto_review.cmd       # 暂停
  resume_auto_review.cmd      # 恢复
  control_auto_review.ps1     # 状态/任务开关的实际脚本
  register_task.ps1           # 22:00 A股/crypto 任务
  register_us_task.ps1        # 06:00 美股刷新任务
site/
  index.html                  # 首次发布用的页面
  reports/latest.md           # 报告原文
  .nojekyll
```

## 没有 Git?

本机当前没有 `git` / `gh`，也没有 GitHub 登录信息。`airhaiseng` 账号和 `icandothatoneday` 仓库（已 Public）确认存在，但无法从本机直接推送。最简单的做法：

- 用 GitHub 网页直接上传本目录；
- 或安装 GitHub Desktop / Git 后再推送；
- 或在有权限的机器上执行 `git init && git add . && git commit && git push`。

不要把 GitHub token 直接发在聊天里；用本机凭据管理器或 GitHub Desktop 登录更安全。

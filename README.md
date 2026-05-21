# 热点概念追踪 · 个人博客自动发布

> 将「今天炒什么」热点概念报告自动部署到 GitHub Pages，每天早上 9:00 自动生成并发布。

---

## 📁 文件说明

```
热点概念自动发布包/
├── .github/
│   └── workflows/
│       └── daily-hot-stocks.yml    # GitHub Actions 自动部署脚本
├── fetch_and_render.py              # 数据抓取 + HTML 渲染脚本
├── template.html                    # HTML 页面模板（完整UI）
└── README.md                        # 本文件
```

---

## 🚀 部署步骤（5分钟完成）

### Step 1：上传文件到 GitHub

**方式一：网页操作（推荐新手）**
1. 打开 https://github.com/misslizy3715/Stefanie
2. 点击 `Add file` → `Upload files`
3. 将 `热点概念自动发布包` 文件夹内的 **所有文件** 拖入上传区
4. Commit message 填写 `Initial setup: hot stocks auto-deploy`
5. 点击 `Commit changes`

**方式二：Git 命令行**
```bash
git clone https://github.com/misslizy3715/Stefanie
cd Stefanie
# 将文件复制进来
git add .
git commit -m "Initial setup: hot stocks auto-deploy"
git push origin main
```

---

### Step 2：配置 GitHub Secrets

**生成 neodata Token：**
1. 打开 https://github.com/settings/tokens/new
2. 选择权限：`repo` (Full repository access)
3. 生成 Token，复制保存（只显示一次）
4. 打开 https://github.com/misslizy3715/Stefanie/settings/secrets/actions
5. 点击 `New repository secret`
6. Name: `NEODATA_TEMP_TOKEN`，Value: 粘贴你的 Token
7. 点击 `Add secret`

> 💡 **Token 从哪里来？**
> - 打开 WorkBuddy → 金融数据查询 → 任意查询一次
> - 在 API 响应中复制 `tempToken` 字段的值
> - 或在 `C:\Users\李昱\.workbuddy\.neodata_token` 文件中找到

---

### Step 3：启用 GitHub Pages

1. 打开 https://github.com/misslizy3715/Stefanie/settings/pages
2. Source: **Deploy from a branch**
3. Branch: `main`，folder: `/ (root)`
4. 点击 `Save`
5. 等待 1-2 分钟，你的博客地址将是：
   **`https://misslizy3715.github.io/Stefanie/`**
   或你的自定义域名

---

### Step 4：验证部署

1. 打开 https://github.com/misslizy3715/Stefanie/actions
2. 点击 `Daily Hot Stocks Report` → `Run workflow` → `Run workflow`
3. 查看 `Actions` 标签页，等待任务完成（绿色 ✅）
4. 访问你的博客地址，确认页面正常显示

---

## ⏰ 自动运行时间

| 触发方式 | 时间 | 说明 |
|---------|------|------|
| **自动** | 每天 09:00（北京时间）| 周一至周五交易日 |
| **手动** | 随时 | GitHub Actions 页面手动触发 |
| **推送** | 推送代码时 | 可选配置 |

> ⚠️ GitHub Actions 使用 UTC 时间，配置 `0 1 * * 1-5` = 北京时间周一至周五 09:00

---

## 🔧 自定义修改

### 修改自动发布时间
编辑 `.github/workflows/daily-hot-stocks.yml` 中的 cron 表达式：
```yaml
schedule:
  - cron: '0 1 * * 1-5'   # 北京时间周一至周五 09:00
  # - cron: '0 9 * * *'   # UTC 09:00 = 北京时间 17:00
```

### 修改博客地址
在 GitHub Settings → Pages → Custom domain 中填入你的域名即可。

### 修改展示概念数量
编辑 `fetch_and_render.py` 中的 `[:6]` → `[:10]` 可展示更多概念。

---

## ❓ 常见问题

**Q: 页面显示"暂无数据"？**
→ 检查 `NEODATA_TEMP_TOKEN` 是否正确配置，或手动触发 Actions 查看日志报错。

**Q: GitHub Pages 404？**
→ 等待 2 分钟让部署完成；检查 Settings → Pages 的 Source 设置是否正确。

**Q: 想改为自定义域名？**
→ 在 Pages 设置中添加域名，并配置 CNAME 记录指向 `misslizy3715.github.io`

---

## 📝 本地调试

```bash
# 安装依赖
pip install requests

# 本地运行（需先从 WorkBuddy 获取 token）
export NEODATA_TEMP_TOKEN="你的token"
python fetch_and_render.py

# 打开 index.html 预览效果
```

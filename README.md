# 🍔 UMelb Freebies

自动收集墨尔本大学学生会的免费食品和福利活动，生成 ICS 日历供 Outlook 订阅。

## 项目目的 / Purpose

从 UMSU 官方活动页面自动抓取免费活动，筛选未来 14 天内的活动，生成 `freebies.ics` 日历文件，通过 GitHub Pages 发布，供 UoM Outlook 使用 "Subscribe from web" 订阅。

## 架构 / Architecture

```
UMSU 官方活动页面
→ GitHub Actions 每天自动抓取
→ 筛选免费活动（未来 14 天）
→ 生成 docs/freebies.ics
→ GitHub Pages 发布
→ Outlook Subscribe from web
```

## 数据源 / Data Sources

| 来源 | URL | 说明 |
|------|-----|------|
| Free Food 列表 | `https://umsu.unimelb.edu.au/ents/eventlist/free-food/` | 官方免费食品活动 |
| Free 列表 | `https://umsu.unimelb.edu.au/ents/eventlist/free/` | 官方免费活动 |
| 所有活动 | `https://umsu.unimelb.edu.au/things-to-do/events/` | 全部活动（按标签筛选） |

## 免费筛选规则 / Filtering Rules

- **一级**：免费食品（Free breakfast/lunch/BBQ/pizza/coffee/food/drinks/snacks 等）
- **二级**：免费福利（Free gift/merchandise/books/workshop/movie/game 等）
- **排除**：收费活动、普通课程、无法确认日期/时间的活动、已结束的活动
- 无法确认是否免费时，宁可不加入

## 本地运行 / Run Locally

```bash
pip install -r requirements.txt
python src/build_calendar.py
```

输出文件：`docs/freebies.ics`

## 启用 GitHub Actions

1. 将项目推送到 GitHub 仓库
2. 进入仓库 → Settings → Actions → General → Allow all actions
3. Workflow 将每天墨尔本时间约 20:00（UTC 09:00）自动运行
4. 也可在 Actions 页面手动触发（workflow_dispatch）

## 启用 GitHub Pages

1. 进入仓库 → Settings → Pages
2. Source 选择 **Deploy from a branch**
3. Branch 选择 **main**，Folder 选择 **/docs**
4. 点击 Save

## 获取 ICS URL / Get ICS URL

GitHub Pages 启用后，URL 格式为：

```
https://<YOUR_USERNAME>.github.io/umelb-freebies/freebies.ics
```

## 在 Outlook 订阅 / Subscribe in Outlook

1. 打开 Outlook Web 或桌面版
2. 选择 **Add calendar** → **Subscribe from web**
3. 粘贴上面的 ICS URL
4. 点击 Import

> ⚠️ **请使用 "Subscribe from web"，不要使用 "Upload from file"**
> Upload from file 是一次性导入，不会自动更新。
> Subscribe from web 才能持续获取最新活动。

## 常见问题 / FAQ

**Q: 为什么没有看到某个免费活动？**
A: 可能是活动没有标记 "Free Food" 或 "Free" 标签，或者活动页面信息不足无法确认是否免费。程序遵循"宁可不加入，不要猜测"的原则。

**Q: Outlook 日历多久刷新一次？**
A: Outlook 会定期检查订阅的 ICS URL。GitHub Actions 每天 20:00（墨尔本时间）更新文件。

**Q: 如果所有数据源都失败了会怎样？**
A: 程序会生成一个空的合法 ICS 文件，并在日志中输出 `WARNING: all sources failed`。

## 当前限制 / Limitations

- 仅支持 UMSU 官方活动页面作为数据源
- 不支持需要登录的功能（如 Outlook API）
- 活动是否收费的判断基于文本关键词，可能存在误判
- 依赖 UMSU 网站结构，如网站改版可能需要更新解析逻辑

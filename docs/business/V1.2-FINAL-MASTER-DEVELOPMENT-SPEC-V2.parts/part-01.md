# 中文网络文学平台 V1.2 最终主开发文档（全量冻结版）

> **文档定位**：这是 V1.2 第一阶段 Web 平台的最终主开发文档。  
> **用途**：给产品、前端、后端、数据库、QA、DevOps、Codex/AI 开发代理共同使用。  
> **优先级**：若代码、旧文档、临时实现与本文件冲突，以本文件中的“冻结规则”为最高优先级。  
> **开发目标**：不是 Demo，而是商业级、可真实收费、可签约作者、可结算、可风控、可运营、可审计、可扩展的中文网络文学平台。  
> **开发方式**：Codex 采用依赖感知的多 Workstream 并行直线开发，不要求用户逐模块喂提示词。  
> **技术栈**：保持此前冻结方案不变，见“第十二篇：最终技术栈与工程架构”。

---

# 第一篇：先明确三个端到底做什么

本项目第一阶段只做 Web，一共三个前端：

```text
Reader Web
Writer Center
Admin Console
        ↓
API Gateway / BFF
        ↓
统一 Application / Domain Layer
        ↓
MySQL / Redis / RabbitMQ / OpenSearch / ClickHouse / Object Storage
```

核心原则：

> 三个端可以拥有完全不同的页面、DTO 和权限，但不能拥有三套“作品真相”“钱包真相”“作者真相”。

例如：

```text
Reader看到：
书名、封面、简介、公开章节、价格、评分

Writer看到：
草稿、审核状态、签约状态、收益、责任编辑

Admin看到：
内部审核、风险、版权、运营、审计
```

但它们最终读取的仍然是同一个 `Book Domain`。

---

# 第二篇：Reader Web —— 完整产品功能 + 前后端 + 数据实现

## 1. Reader Web 顶部导航

固定建议：

```text
Logo
首页
书库
排行榜
完本
免费
书单
作家专区
搜索
消息
登录 / 头像 / 个人中心
```

Reader 的视觉方向继续冻结：

> **起点式信息密度 + 番茄式现代清爽感。**

不能直接把 Element Plus 默认后台组件拿来拼 Reader。

---

## 2. 游客权限

游客不强制登录。

### 游客能做

- 浏览首页
- 浏览书库
- 浏览排行榜
- 浏览完本/免费/书单
- 搜索
- 看作品详情
- 阅读免费章节
- 使用允许的基础 TTS
- 看公开作者主页
- 看公开评论/书评/书友圈内容

### 游客不能做

- 云端书架
- 云端阅读进度
- 评论/回复/点赞
- 关注作者
- 创建/收藏书单
- 投月票/推荐票
- 送礼物
- 购买 VIP
- 充值
- 会员
- 钱包
- 资产操作
- 用户通知
- 客服资产类工单

### 实现方式

游客阅读进度：

```text
Browser localStorage / cookie
```

登录时：

```text
本地进度
        +
账号云端进度
        ↓
明确提示用户
“是否同步本设备阅读进度？”
```

不能：

```text
登录
↓
直接用游客本地旧进度
覆盖账号最新云端进度
```

---

## 3. 登录 / 注册

第一阶段支持：

```text
手机号 + 密码
手机号 + 验证码
登录名 + 密码
微信
QQ
```

暂不做邮箱。

### 第三方登录

首次：

```text
微信/QQ OAuth
↓
未知第三方身份
↓
要求绑定/验证手机号
↓
若手机号已有相关账号
    → 允许链接已有账号
否则
    → 创建新 PlatformAccount
```

后续：

```text
微信/QQ
↓
直接命中绑定账号
↓
登录
```

### 手机号不是 Account

冻结规则：

> 手机号可以关联多个 PlatformAccount。

因此禁止设计：

```text
platform_accounts.phone UNIQUE
```

正确关系：

```text
Phone LoginIdentity
      │
      ├── Account A
      ├── Account B
      └── Account C
```

再使用：

```text
login_identity_routing
```

记录手机号默认登录账号。

### 例子

手机号 `138****0000` 关联：

```text
Account A：普通读者
Account B：作者账号
Account C：备用账号
```

手机号验证码登录：

```text
手机号认证成功
↓
进入默认Account B
↓
个人中心可切换 Account A / C
```

资产永远不合并。

---

## 4. 实名体系

普通读者不强制实名。

以下场景强制：

```text
充值前
申请作者前
```

快速实名建议：

```text
SMS验证
↓
姓名
↓
身份证
↓
人脸
↓
失败时人工兜底
```

### 冻结规则

同一身份证最多实名认证：

```text
3 个 PlatformAccount
```

### 为什么不能只做 UNIQUE(identity_id)

因为一个实名主体合法对应最多 3 个账号。

正确模型：

```text
RealNameSubject
      │
      ├── Account A
      ├── Account B
      └── Account C
```

### 数据库实现

`real_name_subjects`

```text
id
id_fingerprint UNIQUE
encrypted_name
encrypted_id_number
```

`account_real_name_links`

```text
account_id UNIQUE
real_name_subject_id
slot_status:
    ACTIVE
    PENDING_RELEASE
    RELEASED
    BLOCKED_BY_VIOLATION
```

### 并发必须这样做

同一身份证同时 4 个账号发起实名：

```text
Transaction
↓
SELECT RealNameSubject FOR UPDATE
↓
统计 ACTIVE/PENDING_RELEASE/BLOCKED
↓
>=3 → 拒绝
<3  → 创建Link
```

最终必须：

```text
最多3个成功
```

### 不能做

不能：

```text
同身份证一个账号违规
↓
自动封禁另外两个账号
```

正确：

```text
违规Account处罚
↓
Sibling accounts增加关联风险Signal
↓
独立Risk Review
```

---

## 5. Reader 首页

首页模块建议：

```text
主Banner
编辑精选
男频精选
女频精选
热读
畅销
新书
新人
完本
免费
会员
官方书单
专题
活动
```

### 后端实现

```text
page_layouts
page_layout_versions
page_modules
resource_slot_definitions
resource_placements
resource_placement_items
```

首页不是把所有书写死在 Vue 代码里。

### 例子

今天：

```text
01 Banner
02 编辑精选
03 热读榜
04 新书
```

国庆活动：

```text
01 国庆Banner
02 国庆专题
03 编辑精选
04 热读榜
```

活动结束恢复原布局。

因此不能：

```sql
UPDATE page_modules SET sort_order = ...
```

不断覆盖历史。

正确：

```text
Layout V7
↓
Layout V8（国庆）
↓
定时生效
↓
活动结束回到V9
```

---

## 6. Banner

Banner 素材和 Banner 投放必须分开。

```text
banner_creatives
        ↓
resource_placements
```

### 为什么

同一张素材可以：

- 首页使用
- 专题使用
- 不同时间段复用

### 跳转

```text
BOOK
BOOKLIST
ACTIVITY
MEMBERSHIP
INTERNAL_PAGE
EXTERNAL_URL
```

外链需要更高审核，禁止任意 Open Redirect。

---

## 7. 搜索

支持：

```text
书名
历史书名
作者笔名
历史笔名
人物名
标签
简介关键词
搜索建议
搜索历史
热搜
错别字纠正
同义词
分类筛选
状态筛选
排序
分页
```

### 数据实现

MySQL：

> 作品事实真相。

OpenSearch：

> 搜索 Projection。

### 不能做

不能：

```sql
SELECT * FROM books
WHERE title LIKE '%关键词%'
OR synopsis LIKE ...
```

承担全站公共搜索。

### 作者知识库

作者私有：

```text
世界观
人物设定
伏笔
大纲
```

禁止进入公共 Search Index。

---

## 8. 排行榜

正式榜：

```text
热读
畅销
月票
推荐
收藏
打赏
新书
新人
完本
更新
免费
会员
```

支持男频/女频和榜单自己的周期。

### 核心数据

```text
ranking_definitions
ranking_rule_versions
ranking_snapshots
ranking_entries
ranking_contributions
ranking_exclusions
```

### 能做

运营首页可以：

```text
展示“月票榜”模块
```

### 不能做

运营不能：

```text
“把Book A改成月票榜第一”
```

Ranking Entry 必须来自：

```text
规则版本
+
NORMAL有效贡献
+
Snapshot
```

### 活动榜

国庆活动可以有：

```text
国庆阅读挑战榜
```

但必须标明：

> 活动榜

不能伪装正式平台月票榜。

---

## 9. 作品详情页

至少展示：

```text
书名
封面
简介
作者
分类
标签
状态
总字数
更新时间
最新章节
VIP状态
会员书库状态
限免状态
评分
短评/长评
粉丝值
荣誉
排行
相关推荐
加入书架
开始/继续阅读
投票
礼物
目录
```

### Reader DTO

不能包含：

```text
internal_risk_score
contract_internal_note
editor_staff_id
审核内部证据
```

这些字段不是“传NULL”，而是 Reader DTO 里根本不存在。

---

## 10. 阅读器

支持：

```text
滚动
分页
自动阅读
字号
行距
字体
背景
夜间
章节切换
目录
书签
进度
段评
TTS
VIP购买
自动订阅
```

### Chapter Access Service

冻结顺序：

```text
1. Book/Chapter availability
2. Account reading restriction
3. FREE
4. PURCHASED
5. LIMITED_FREE
6. MEMBER_FREE
7. VIP_REQUIRED
```

### 例子1：已购

章节现在：

```text
VIP
```

用户有：

```text
ChapterEntitlement
```

结果：

```text
PURCHASED
→ ALLOW
```

即使会员已过期，也继续允许。

### 例子2：会员

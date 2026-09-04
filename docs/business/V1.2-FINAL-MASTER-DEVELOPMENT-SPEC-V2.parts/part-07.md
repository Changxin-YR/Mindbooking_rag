CI
```

真实收费前：

```text
M5治理能力必须达到
```

包括：

```text
Wallet
Payment签名
回调幂等
Refund
Chargeback
Reconciliation
Risk
Support
Approval
Audit
Encryption
RateLimit
Backup
PITR
Monitoring
P0 Alert
```

---

# 第十八篇：Codex实现时的最高工程原则

> 1. **先按三个端理解产品，再按 Domain 落后端，再按 ER/表设计落数据库。**  
> 2. **业务规则必须通过例子和 Golden Test 固化，不能只靠注释。**  
> 3. **能做什么、不能做什么必须落实到 Permission、Service Boundary、DB Constraint 和 Test。**  
> 4. **Ledger是真相，Balance是投影。**  
> 5. **版本不可覆盖，历史必须可追。**  
> 6. **跨Domain禁止直接写表。**  
> 7. **Agent、Admin、Support、Risk 都不是数据库超级管理员。**  
> 8. **开发可以并行，但业务依赖不能被并行“绕过去”。**  
> 9. **Codex不等待用户逐模块喂任务，应自主连续推进。**  
> 10. **最终目标是一次性得到可运行、可测试、可验收的完整 V1.2，而不是大量半成品。**



---

# 第十九篇：从《三端完整冻结版 V1.2》恢复并补齐的功能（V2 必须实现）

> 本篇用于补齐此前主开发文档中被压缩、遗漏或只保留了架构而没有保留产品细节的功能。  
> **本篇不是“可选建议”，除明确写“预留/参数待定”的项目外，均纳入 V1.2 实现范围。**  
> 若旧例子与后续最新冻结规则冲突，以后续最新冻结规则为准。例如：充值退款现在必须额外扣除“同源充值促销赠币自然过期部分的等值金额”；旧版只扣已消费赠币的示例不再作为最终公式。

## 136. Reader：男女频与首次进入

平台支持：

```text
男频
+
女频
```

但用户第一次进入：

```text
不强制选择性别
```

推荐系统可以根据阅读兴趣逐渐建立偏好。

### 前端

Reader 首页、书库、榜单均可以切换男频/女频。

### 后端

频道是作品与场景维度，不把“用户性别”当作强制画像字段。

### 不能做

不能：

```text
首次打开网站
↓
必须选“男/女”
↓
不选不能继续
```

也不能因为用户浏览男频就推断其真实生理性别。

---

## 137. Reader：书库完整筛选

书库需要：

```text
频道
主分类
子分类
标签
作品状态
字数范围
免费/VIP
更新时间
签约状态（公开可展示口径）
```

例如：

```text
主分类：玄幻
子分类：东方玄幻
标签：系统、穿越、升级、热血
状态：连载
字数：100万以上
```

### 数据

复用：

```text
categories
tags
book_metadata_version_tags
books
book_monetization_policy_versions
```

筛选查询使用 Search Projection，而不是让前端拼接任意 SQL 条件。

---

## 138. Reader：评分系统补齐

作品评分除了总分，可支持：

```text
剧情
人物
文笔
更新
```

只有满足一定有效阅读条件的账号才能提交评分。

### 例子

```text
用户只点开作品详情，没读正文
→ 不允许直接刷1星/5星

用户达到平台配置的有效阅读阈值
→ 可以评分
```

### 数据建议

```text
book_user_ratings
book_user_rating_versions
```

当前评分：

```text
UNIQUE(account_id, book_id)
```

建议字段：

```text
overall_score
plot_score
character_score
writing_score
update_score
eligibility_metric_version_id
eligibility_snapshot_ref
```

历史修改保存在 Version 表。

### 不能做

不能只根据“是否登录”允许评分。

---

## 139. Reader：阅读设置完整项

至少：

```text
字体
字号
字重
行高
段距
正文宽度
白色
米黄
护眼
灰色
深色
段评开关
全屏
沉浸模式
滚动/分页
自动滚动
```

设置可以：

```text
本地即时生效
+
登录用户云端同步
```

### 数据

```text
reading_preferences
```

普通视觉设置不是财务真相，不需要复杂 Event Sourcing。

---

## 140. Reader：关注系统与用户公开主页

支持：

```text
关注作者
关注普通用户
```

关注作者可以订阅：

```text
新章节
新书
作者动态
公告
活动
```

普通用户公开主页可以展示其主动公开的：

```text
头像
昵称
用户等级
勋章
关注/粉丝
公开书单
公开书评
公开动态
```

### 数据

```text
follow_relations
profile_privacy_settings
user_growth_profiles
```

`follow_relations.target_type`：

```text
AUTHOR
ACCOUNT
```

### 隐私

阅读历史默认私密。

用户可以控制：

```text
书架是否公开
书单是否公开
关注列表是否公开
粉丝等级是否公开
勋章是否公开
个性化推荐
```

### 不能做

不能把用户阅读历史默认展示在公开主页。

---

## 141. Reader：用户成长等级

用户成长等级与以下全部分开：

```text
会员等级
作品粉丝等级
作者成长等级
```

成长来源可包括：

```text
阅读
活跃
互动
平台贡献
```

### 数据

```text
user_growth_profiles
user_growth_events
user_growth_rule_versions
```

这是成长体系，不是钱包资产。

---

## 142. Reader：纠错与举报

正文纠错类型：

```text
错别字
章节重复
章节缺失
排版错误
内容违规
版权问题
其他
```

社区举报：

```text
广告
人身攻击
色情低俗
刷屏
侵权
违法内容
其他
```

### 实现

普通内容举报进入统一 Governance/Report Case。

版权问题跳转/升级到 Copyright Complaint，不和普通举报混为一个案件模型。

正文排版/错别字类可进入：

```text
content_correction_reports
```

并允许作者/编辑查看必要问题位置，但不得暴露举报人的私密身份。

---

## 143. Reader：未成年人保护

此前冻结为完整预留，V1.2 至少要把数据结构、策略接口、前端入口和限制钩子做完整，不硬编码尚未最终确认的具体数值。

预留：

```text
年龄识别
未成年人模式
内容推荐限制
消费限制
高额礼物限制
互动限制
阅读时间提醒
监护机制
```

### 数据建议

```text
minor_protection_profiles
minor_protection_policy_versions
minor_protection_events
guardian_links
```

### 规则

具体金额、时间阈值通过政策版本配置，不散落代码。

---

# 第二十篇：Writer Center 补齐

## 144. 作者改笔名

未签约、无重大商业影响时：

```text
允许有限修改
```

签约后：

```text
申请
↓
编辑/平台审核
↓
风险/冒充检查
↓
生效
```

必须保存：

```text
pen_name_history
```

历史笔名继续可搜索。

---

## 145. 作品封面完整校验

支持：

```text
作者上传
平台模板
AI生成
```

检测：

```text
尺寸
比例
清晰度
文件大小
内容违规
版权风险
```

业务表只保存 `file_id` / cover version，不接受任意公网 URL 作为可信封面。

---

## 146. 首发审核范围可配置

首次正文审核不是只能审“第一章”。

后台策略可设置：

```text
前N章
或
前N字
```

### 实现

`review_policy_versions` 保存首发采样策略。

Review Submission 绑定固定章节 Version 集合。

---

## 147. 章节状态：UI状态与数据库状态分离

旧产品 UI 可以显示：

```text
草稿
定时发布
审核中
已发布
审核驳回
已下架
```

但数据库不能把这些全部塞进一个万能 `chapter.status`。

最终实现继续采用：

```text
publish_state
visibility_state
review state（Review Domain）
commercial policy（Commerce/Content Policy）
```

Writer BFF 根据多维状态生成 UI 文案。

### 例子

```text
publish_state = SCHEDULED
review = APPROVED
visibility = PRIVATE_UNTIL_SCHEDULE
```

前端可以显示：

```text
“已审核，等待定时发布”
```

而不是创造一个新的数据库真相枚举。

---

## 148. 发布前预检

至少检查：

```text
敏感词
违法风险
色情低俗
攻击内容
广告导流
重复内容
乱码
异常字符
章节过短
排版问题
```

普通问题：

```text
提醒
```

严重问题：

```text
阻止提交 / 进入人工复核
```

预检结果不等于最终审核决定。

---

## 149. 已发布章节修改分层

免费章节：

```text
普通纠错
→ 新Version，可走低风险审核流程

重大修改
→ 新Version + 重审
```

VIP章节：

```text
小范围纠错
→ 新Version

大量替换
→ 重审

大幅减少字数
→ 风控/商业影响检查
```

任何情况保留版本历史。

---

## 150. 作者公告、动态与投票

作者公告：

```text
更新说明
请假
加更
活动
完结感言
新书通知
普通公告
```

作者动态：

```text
创作日常
剧情预告
写作感想
互动话题
```

作者投票：

```text
互动投票
```

但投票不能改变：

```text
平台规则
合同
审核结果
商业政策
```

---

## 151. 作者公开主页

展示：

```text
头像
笔名
签约标识
代表作
粉丝
作者简介
全部作品
连载
完结
动态
公告
书单
荣誉
```

同身份证的其他账号：

```text
前台永远不显示实名关联
```

---

## 152. 作者评论管理权限

作者可以：

```text
回复
点赞
置顶
举报
```

平台可以：

```text
平台精选
平台置顶
```

### 最终权限修正

旧基线中的“作者加精”不作为最终平台级精选权限。

作者不得：

```text
删除正常差评
把普通评论标记成平台精选
```

---

## 153. 作者粉丝中心与核心粉丝

作者可以查看聚合数据：

```text
总粉丝
新增
趋势
等级结构

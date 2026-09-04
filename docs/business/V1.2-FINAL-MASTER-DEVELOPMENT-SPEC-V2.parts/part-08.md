月票贡献
推荐票贡献
礼物贡献
互动活跃
```

核心粉丝贡献综合：

```text
订阅
有效阅读
推荐票
月票
礼物
互动
```

作者不能看到：

```text
真实姓名
身份证
完整手机号
银行卡
支付账号
```

---

## 154. 创作日历

展示：

```text
每日字数
本周字数
本月字数
连续更新
断更
定时章节
每日目标
```

### 数据

```text
writing_goals
author_daily_writing_stats
```

每日字数可以从 Draft/Version 写入事件聚合，不把“统计数字”手工写回章节正文。

---

## 155. 作者任务

类型：

```text
新手任务
成长任务
更新任务
活动任务
运营任务
```

奖励可能：

```text
勋章
积分
奖金
活动资格
流量权益
推荐资源
```

### 数据

```text
author_task_definitions
author_task_rule_versions
author_task_progress
```

奖励必须走 Reward Center / AuthorFinance / Operation Service。

作者奖金不能直接改 Writer “余额”。

---

## 156. 作者成长等级

示例层级：

```text
新作者
签约作者
潜力作者
精品作者
优秀作者
头部作者
```

综合：

```text
作品质量
更新稳定
阅读表现
商业数据
违规记录
平台贡献
```

### 数据

```text
author_growth_profiles
author_growth_events
author_growth_rule_versions
```

等级规则版本化。

---

## 157. 创作活动中心

页面：

```text
进行中
即将开始
已结束
我的活动
```

活动可包括：

```text
征文
新人扶持
年度大赛
更新挑战
完本奖励
短篇比赛
IP改编征集
```

复用 Operation Campaign/Reward/Risk，不再造第二套活动引擎。

---

## 158. 创作学院

内容：

```text
新手
人物
剧情
世界观
节奏
开篇
长篇
平台规则
签约
数据
版权
```

形式：

```text
文章
视频
课程
案例
直播回放
```

### 数据建议

```text
writer_learning_categories
writer_learning_contents
writer_learning_progress
```

内容由运营 CMS 管理，禁止任意不受控 JavaScript/HTML。

---

## 159. 作者推荐申请边界

普通算法流量：

```text
作者不能申请“给我更多算法曝光”
```

活动/征文：

```text
作者可以报名
```

重大首页推荐：

```text
编辑/运营决定
```

防止把 Recommendation 变成人工申请队列。

---

## 160. 作者数据中心补齐

除已有核心指标外，还要支持：

```text
曝光
详情访问
开始阅读
有效阅读
阅读时长
人均章节
完读率
下一章率
收藏率
新增书架
净增书架
流失
评论
段评
推荐票
月票
礼物
订阅人数
订阅收入
新增付费用户
```

时间：

```text
今日
昨日
7天
30天
自定义
```

全部引用 Metric Center 统一口径。

---

## 161. 逐章漏斗

每章：

```text
进入人数
完读率
下一章率
订阅转化
评论
段评
```

用于定位流失章节。

数据来自 Validated Reading Facts + Commerce Facts，不直接实时扫 raw reading events。

---

## 162. 免费作品分成

继续采用：

```text
平台免费阅读扶持池
```

未来如果引入广告：

```text
广告净收入
+
平台补贴
```

可以进入扶持池。

实际分配使用有效阅读等统一 Metric + 风控清洗，再按合同分成。

---

## 163. 作者违规与申诉

Writer 必须能看到：

```text
违规作品/章节
问题位置
规则
原因
处罚
整改要求
申诉入口
进度
结果
```

申诉由独立复审处理，原决策人员不能自己复审自己的决定。

---

## 164. 多人创作

最终冻结：

```text
完全不做
并且不预留
```

不存在：

```text
联合作者
共同署名
多人章节权限
作者间分成
```

一本作品只归属一个 AuthorProfile。

---

# 第二十一篇：Admin Console 补齐

## 165. Review Rule Library

统一管理规则：

```text
违法
色情低俗
暴力极端
广告导流
侵权
仇恨攻击
未成年人风险
诈骗
敏感信息
版权风险
平台规则
```

每条规则至少：

```text
rule_code
severity
recommended_action
auto_block_policy
subject_types
version
effective_from
```

---

## 166. 审核结果结构化

审核不能只有自由文本“通过/不通过”。

至少：

```text
通过
条件通过
退回修改
人工复审
下架
封禁提案
```

驳回/整改：

```text
问题类型
问题位置
规则编号
风险等级
整改要求
审核说明
```

机器结果、人审结果、最终决定分别保存。

---

## 167. 审核队列与 SLA

路由考虑：

```text
风险等级
内容类型
频道
作者风险
审核员专业领域
SLA
```

SLA 策略可针对：

```text
普通章节
新作品
高风险内容
P0内容
```

分别配置。

---

## 168. 审核员质量

后台指标：

```text
准确率
误杀率
漏审率
复审推翻率
处理时间
投诉率
```

不能只以“处理速度”考核审核员，否则会诱发误杀/漏审。

---

## 169. 内容处罚分层

例如：

```text
单章问题
→ 单章下架

多次违规
→ 发布限制

严重
→ 整书下架

更严重
→ 作者处罚
```

不能一次普通社区违规就影响用户已经购买的阅读权益。

---

## 170. 签约评估

结构化维度：

```text
内容质量
题材市场
开篇
追读
收藏率
更新稳定
作者历史
商业潜力
版权潜力
风险
```

结论：

```text
建议签约
继续观察
不建议
```

编辑建议不等于签约已生效。

---

## 171. 作者异常预警

自动提醒责任编辑：

```text
连续多天断更
追读突然下降
负面评论激增
退款异常
审核频繁失败
```

来自 Metric/Risk/Content 事件。

责任编辑看到的是业务摘要，不需要访问所有底层敏感风险数据。

---

## 172. 新书冷启动与潜力新作

冷启动池至少区分：

```text
新人新书
签约新书
成熟/头部作者新书
```

候选来源：

```text
算法
编辑提名
运营提名
```

统一进入候选池。

目的：

> 避免头部作者完全挤压新人。

---

## 173. 编辑精选说明

人工精选必须记录：

```text
推荐理由
适合人群
作品亮点
```

若是 Recommendation Ops Override：

```text
原因
开始
结束
修改人
```

必须审计。

---

## 174. A/B Test

首页/推荐资源支持：

```text
A
B
```

观察：

```text
曝光
CTR
开始阅读
收藏
订阅
收入
负反馈
```

使用统一 Experiment Service。

财务价格、退款等高风险金融规则不能混入普通 UI A/B。

---

## 175. 推荐排期

运营后台需要：

```text
推荐资源日历
```

规划：

```text
Banner
编辑精选
频道推荐
活动资源
```

并检查同一资源位时间冲突。

---

## 176. 用户360档案

后台 Query View 聚合：

```text
基本信息
实名状态
会员
成长等级
资产
充值
消费
阅读
书架
投票
礼物
社区内容
举报
账号风险
支付风险
社区风险
关联账号风险
```

### 重要

这是 Query Service / Read Model。

不能建立一张“user_360”大表把所有 Domain 真相复制一遍。

所有字段按 Staff Permission / Data Scope / Sensitive Classification 脱敏。

---

## 177. 社区动态审核

低风险：

```text
可实时展示
```

中风险：

```text
HOLD / 人工
```

高风险：

```text
拦截 / Case
```

高风险账号可提高审核等级。

---

## 178. 用户处罚状态与限制项分开

账号整体状态不要只有 `banned=true`。

至少支持：

```text
NORMAL
COMMUNITY_RESTRICTED
PAYMENT_RESTRICTED
SECURITY_FROZEN
LOGIN_SUSPENDED
TERMINATED
```

并支持 action-level restrictions：

```text
COMMENT
COMMUNITY_POST
LIKE
VOTE
GIFT
RECHARGE
ACTIVITY
LOGIN
PURCHASE

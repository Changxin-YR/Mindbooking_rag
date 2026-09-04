```

角色多选，权限取并集。

Data Scope：

```text
OWN
TEAM
DEPARTMENT
ASSIGNED
ALL
CUSTOM
```

### 例子

责任编辑：

```text
book.read
data_scope = ASSIGNED
```

只能看：

```text
分配给自己的作品
```

即使另一本作品 ID 被手工改进 URL：

```text
后端仍拒绝
```

---

## 53. Sensitive权限

L3：

```text
实名
银行卡
合同
法律证据
```

前端不能：

```text
先把完整身份证发给浏览器
再用****遮住
```

正确：

```text
Server-side masked DTO
```

查看完整值需要：

```text
specific permission
+
reason/case
+
SensitiveAccessLog
```

---

## 54. Review Center

流程：

```text
Submission
↓
Machine Review（可选）
↓
Queue
↓
Human Task
↓
Decision
↓
Domain executes
```

审核绑定固定Version。

### 首发

必须人工。

### 高风险

普通 Reviewer 不可永久下架：

```text
Reviewer propose
↓
Approval
↓
ContentService execute
```

---

## 55. Editor Workspace

责任编辑负责：

```text
作品
作者
签约
倒V
完结
会员书库确认
编辑推荐
工作消息
```

Reviewer负责：

```text
合规审核
```

不能把两类职责混成一个“审核编辑”。

---

## 56. Operation Center

### 能做

```text
首页布局
Banner
编辑精选
专题
活动
限免
会员书库提案
官方书单
作者活动
用户活动
Reward
分群
排期
```

### 不能做

```text
直接改Ranking rank
直接改Wallet
直接改AuthorRevenue
直接改Chapter VIP字段
直接改正文
```

---

## 57. 编辑推荐

可以：

```text
Manual Curated Slot
```

必须写：

```text
editorial_reason
```

例子：

```text
推荐原因：
新书节奏稳定，30章追读表现良好，
题材符合本周仙侠专题。
```

---

## 58. 资源位与榜单区别

编辑精选：

```text
人工排序允许
```

正式榜单：

```text
人工改rank不允许
```

这是两个完全不同业务。

---

## 59. 会员书库

固定工作流：

```text
会员/内容运营提案
↓
责任编辑确认
↓
合同/收益自动检查
↓
特殊情况财务/商务
↓
Approval
↓
MembershipService创建LibraryEntry
```

Operation 不能直接把：

```text
chapter.vip = false
```

---

## 60. 限时免费

```text
limited_free_campaign
```

只是 Access Override。

不能修改 VIP 商业事实。

活动结束自动恢复原访问判断。

---

## 61. Reward Center

奖励：

```text
GiftCoin
Ticket
Membership Days
Badge
Author Cash Reward
Traffic Resource
```

Reward Center 不直接写资产表。

例如：

```text
活动奖励500赠币
```

正确：

```text
RewardOrder
↓
Risk
↓
WalletService.grantGiftCoin
↓
GiftCoinLot(origin=ACTIVITY)
```

不是：

```sql
UPDATE wallet_balances SET gift_coin=...
```

---

## 62. 充值活动

例如：

```text
充100送2000赠币
```

Operation只配置 Campaign。

真正：

```text
Payment/Wallet policy
```

负责金额、赠币批次、退款追溯。

---

## 63. Support Center

客服：

```text
受理
调查
解释
协调
发起流程
```

不能：

```text
直接返钱
直接加币
直接解冻Risk
直接改作者收入
```

---

## 64. Support P0 vs Platform P0

用户账号疑似被盗：

```text
Support Ticket P0
```

不一定等于：

```text
Platform Emergency P0
```

只有大规模平台级事故才进入 EmergencyIncident。

---

## 65. 工单状态

```text
NEW
TRIAGING
ASSIGNED
IN_PROGRESS
WAITING_USER
WAITING_INTERNAL
RESOLVED
CLOSED
CANCELLED
```

RESOLVED != CLOSED。

用户在确认期继续回复：

```text
RESOLVED → IN_PROGRESS
```

---

## 66. 客服退款

客服只能：

```text
发起RefundRequest
看RefundCalculation
向用户解释
```

不能编辑公式结果。

---

## 67. Compensation

Refund：

```text
原支付逆向
```

Compensation：

```text
平台额外权益
```

两个按钮、两个流程。

补偿统一走 Reward Center。

---

## 68. Account Recovery

不能用户说：

```text
“手机号丢了”
```

客服直接改手机号。

必须：

```text
Recovery Case
↓
Factors
↓
Risk
↓
Manual Review
↓
IAM安全换绑
```

验证：

```text
旧手机号
设备
登录名
注册信息
支付历史
实名
人脸
第三方绑定
```

---

## 69. Finance Center

查看/处理：

```text
Payment
Recharge
Wallet
Lots
Refund
Chargeback
Reconciliation
Author Revenue
Settlement
Withdrawal
```

高风险资金调整：

```text
Maker
↓
Checker
```

SuperAdmin也不能绕过。

---

## 70. Risk Center

Risk只识别和请求动作。

不能：

```text
risk service直接UPDATE wallet_entries
```

正确：

```text
RiskDecision
↓
RiskAction
↓
WalletService / AuthorFinanceService / TicketService
```

---

## 71. 关联账号

关系图：

```text
Account
↔ Device
↔ IP
↔ RealName
↔ Payment Instrument
↔ Payout Account
```

Relation是：

> 事实

不是：

> 有罪结论。

例如同一个宿舍Wi-Fi：

```text
同IP
```

不能直接封号。

---

## 72. Risk规则

新规则：

```text
OBSERVE
↓
看误伤
↓
ENFORCE
```

不能一上线直接大面积处罚。

---

## 73. Approval Center

核心：

```text
能发起
≠ 能审批
≠ 能执行
```

### 例子：永久下架

```text
Content Reviewer
↓
提出永久下架
↓
Approval Request
↓
Legal/Editor/High-level reviewer（按路由）
↓
APPROVED
↓
ContentService重新校验当前状态
↓
EXECUTED
```

如果审批期间书已恢复/案件变化：

```text
Approval不能无条件执行旧动作
```

---

## 74. Audit Center

记录：

```text
谁
何时
IP
Device
权限
原因
资源
Before
After
结果
Approval
RequestId
TraceId
```

读高敏数据也审计。

---

## 75. Copyright Center

每本书：

```text
Copyright Dossier
```

不能一个：

```text
copyright_status
```

解决所有权利。

按：

```text
DIGITAL_READING
AUDIO
PRINT
COMIC
ANIMATION
SHORT_DRAMA
TV_DRAMA
FILM
GAME
OVERSEAS
TRANSLATION
MERCHANDISING
```

分别记录。

---

## 76. 版权授权冲突

例子：

```text
平台A拥有：
中国大陆 + 中文 + 有声独家
2026-2028
```

现在要授权平台B：

```text
中国大陆 + 中文 + 有声独家
2027-2029
```

必须：

```text
CONFLICT
→ BLOCK / MANUAL LEGAL REVIEW
```

不能靠商务人员自己记忆。

---

## 77. 版权投诉

不能：

```text
随便发一句“他抄袭我”
↓
永久下架
```

流程：

```text
主体验证
↓
权利证明
↓
Evidence
↓
必要临时措施
↓
被投诉方答辩
↓
Counter Notice
↓
Copyright/Legal Decision
↓

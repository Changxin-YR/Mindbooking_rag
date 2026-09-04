WITHDRAW
```

### 例子

用户辱骂：

```text
COMMUNITY_RESTRICTED
```

不能因此：

```text
不让他阅读已经购买的VIP章节
```

除非另有独立合法限制。

---

## 179. 举报聚合、反馈与举报人保护

同一内容 500 人举报：

```text
一个 Report Case
+
500个Report Submission
+
原因占比
```

不是 500 个审核任务。

举报人可以看：

```text
已提交
处理中
已完成
已处理 / 暂未发现违规
```

被举报方：

```text
不能看到举报者身份
```

恶意举报：

```text
频率限制
降低举报权重
警告
严重处罚
```

---

## 180. 社区反导流

检测：

```text
微信号
QQ群
手机号
二维码
非法链接
赌博
色情
诈骗
广告刷屏
```

规则版本化，不在 Vue 中写死正则作为唯一安全层。

---

## 181. 违规证据

即使用户删除内容，有案件需要时保留：

```text
原始内容
图片
发布时间
修改历史
删除时间
举报
审核结果
```

进入 Evidence Snapshot / Legal Hold 时普通 Retention 不得删除。

---

## 182. 社区看板

至少：

```text
评论量
书评量
书友圈帖子
机器拦截
人工审核
举报
成立率
禁言
封禁
申诉
改判率
违规类别
```

指标由 Metric Center 管口径。

---

## 183. 客服工单分类与优先级

分类：

```text
账号登录
实名认证
安全
充值
余额
赠币
退款
消费
会员
VIP
自动订阅
阅读
书架
作品/章节
评论/社区
举报/处罚申诉
作者
版权
其他
```

优先级：

```text
P0 账号/资金严重安全
P1 充值不到账、重复扣款、无法登录
P2 权益异常、章节问题
P3 咨询和建议
```

Support P0 不自动等同 Platform Emergency P0。

---

## 184. 客服看板与满意度

看板：

```text
新增工单
待处理
处理中
完成
首响时间
解决时间
SLA
满意度
重复咨询率
问题趋势
```

CSAT：

```text
非常满意
满意
一般
不满意
非常不满意
```

质量评价可作为 Support QA 数据，不影响用户资产。

---

## 185. 支付成功但业务未入账

必须显式处理：

```text
渠道支付成功
↓
平台业务入账失败
↓
CREDIT_PENDING / REPAIR_REQUIRED
↓
自动补账
+
财务对账
```

Admin 可以显示兼容业务文案：

```text
WAITING_RECONCILIATION
```

但不能把第三方成功支付当成“失败订单”直接丢弃。

---

## 186. 财务日对账

每日至少对：

```text
平台PaymentOrder
微信账单
支付宝账单
Wallet流水
Refund
```

输出：

```text
缺单
重复
金额不一致
退款差异
```

写入：

```text
reconciliation_batches
reconciliation_items
```

---

## 187. ConsumptionOrder

VIP、礼物、会员等消费应该先存在明确业务订单/消费事实，再产生日志和资产流水。

```text
ConsumptionOrder
↓
Wallet Debit
↓
Domain Fulfillment
```

Wallet 不负责猜“这笔扣款到底买了什么”。

---

## 188. 提现失败

典型：

```text
提现失败
↓
记录渠道失败原因
↓
可安全退回时恢复可提现
或
高风险时保持冻结待处理
↓
通知作者
```

不得静默丢失 Withdrawal 状态。

---

## 189. 发票/票据

商业架构补齐：

```text
发票申请
状态
金额
抬头
税号
电子文件
红冲
```

### 数据建议

```text
invoice_requests
invoice_documents
invoice_events
```

具体开票合规规则由财务/法务策略版本确定。

---

## 190. 财务人工调整

必须：

```text
reason
evidence/reference
approval
ledger adjustment
audit
```

不能：

```sql
UPDATE wallet_balances
```

修正用户资产。

---

# 第二十二篇：Risk Center 细粒度补齐

## 191. 设备与登录风险

设备画像至少记录必要风险特征：

```text
device
browser
OS
IP
region
User-Agent
trust state
```

注意这些是 L2 数据，应最小化保存。

异常登录识别：

```text
异常地区
不可能速度
异常设备
异常数量
代理/VPN信号
撞库风险
```

不可能旅行是 Signal，不是自动永久封号。

---

## 192. 暴力破解与短信防刷

暴力破解：

```text
动态限速
验证码
短期保护
风险升级
```

不能：

```text
固定错误5次
→ 永久锁号
```

SMS 风控：

```text
手机号频控
IP频控
设备频控
验证码/滑块
异常阻断
```

---

## 193. 充值与退款套利

充值风险关注：

```text
频繁充值
异常大额
异常地区
共同支付来源
充后立刻退款
反复充退
```

经典套利：

```text
充值
↓
获得赠币
↓
快速消费赠币
↓
申请全额退款
```

账务由最新 Refund Formula 防止资产套利，Risk 再做行为审查。

---

## 194. 刷阅读与刷收藏

刷阅读使用：

```text
阅读时间
速度
滚动
章节停留
设备
IP
账号行为模式
```

异常收藏：

```text
标记贡献无效
↓
不进入推荐/排行
```

不一定直接封号。

---

## 195. 月票/推荐票风险

信号：

```text
批量账号
同设备
同IP
异常票来源
短时间集中投票
```

动作：

```text
先FROZEN
↓
调查
↓
NORMAL恢复
或
INVALIDATED
```

不要直接删除原 Vote 事实。

---

## 196. 礼物、同实名、自刷订阅

重点关系：

```text
同实名
同设备
同IP
同支付来源
账号关联
```

同实名互相消费：

> 不绝对禁止正常行为。

疑似作者自刷：

```text
订单事实可以保留
作者收益 → PENDING_RISK/FROZEN
↓
调查
```

不要为了风控删除真实订单。

---

## 197. 风控黑名单 / Watchlist

区分：

```text
账号
设备
IP
支付工具
实名主体
Payout Account
```

IP 通常只做 Watch，不轻易永久 Block。

人工解除：

```text
原因
证据
Case
审批（按风险）
审计
```

不能覆盖/删除原 Risk History。

---

## 198. P0事件与应急

真正平台 P0：

```text
大规模盗号
大额盗刷
支付平台异常
提现账号批量篡改
数据库疑似泄漏
平台币异常生成
平台级重大安全事故
```

P0 业务应急可以暂停：

```text
充值
退款
提现
礼物
票务
注册
章节发布
社区发帖
```

必须有时限、原因、审计、恢复动作。

不提供普通业务人员“一键关闭整个网站”。

---

# 第二十三篇：版权、数据与平台治理补齐

## 199. 版权风险库

除了 Copyright Case，后台可维护：

```text
重点保护作品
已知盗版来源
高频侵权对象
重复侵权账号
版权预警
```

它是风险/证据辅助库，不代表系统可以自动永久处罚。

---

## 200. 管理驾驶舱

管理层只读看板：

```text
DAU/MAU
新增
留存
阅读
时长
追读
完读
充值
会员
VIP
礼物
付费率
作者
签约
更新
作品
章节
举报
违规
退款
风险
```

全部来自 Metric/Read Model。

### 不能做

管理驾驶舱不能：

```text
点击数字
→ 直接修改真实阅读量/充值额
```

---

## 201. 数据中心只读原则

运营/数据岗位不能直接：

```text
改阅读量
改收藏量
改充值金额
改作者收入
```

需要修正时走对应 Domain 的正式调整/重算流程。

---

## 202. 关键参数审批

例如：

```text
会员价格
VIP价格规则
作者分成
最低提现
赠币规则
退款政策
```

变化：

```text
Draft Version
↓
Domain Validation
↓
Approval
↓
effective_at
↓
Activate
```

不能普通员工保存后立即全站生效。

---

## 203. 员工生命周期

状态：

```text
PENDING_ACTIVATION
ACTIVE
LOCKED
DISABLED
OFFBOARDED
```

离职：

```text
禁用账号
撤销Session
结束Role/Delegation
移交任务/作品
保留历史日志
```

Staff 记录不物理删除。

---


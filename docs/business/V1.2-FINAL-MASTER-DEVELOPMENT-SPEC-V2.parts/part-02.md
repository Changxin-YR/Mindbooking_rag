
章节：

```text
VIP
```

用户没买，但作品正在会员书库：

```text
MEMBER_FREE
→ ALLOW
```

会员到期：

```text
MEMBER_FREE消失
→ VIP_REQUIRED
```

### 例子3：限免

章节本身仍是：

```text
VIP
```

活动期间：

```text
LIMITED_FREE
→ ALLOW
```

活动结束：

```text
LIMITED_FREE失效
→ VIP_REQUIRED
```

注意：

> 限免从来没有修改 ChapterCommercialPolicy 的 VIP 事实。

---

## 11. TTS

TTS 与文本必须使用同一个 ContentAccessService。

错误：

```text
文本需要VIP
TTS直接调用语音服务拿全文
```

正确：

```text
TTS请求
↓
CheckChapterAccess
↓
允许后才生成/返回语音
```

有效阅读统计：

```text
TEXT + TTS重叠时间
```

不能双重计入。

---

## 12. 阅读进度

核心：

```text
book_reading_progress
```

约束：

```text
UNIQUE(account_id, book_id)
```

保存：

```text
last/current position
furthest position
revision
current_session
```

### 为什么要 last 和 furthest

用户已经看第100章，又回去重读第10章。

不能：

```text
furthest = 第10章
```

正确：

```text
last = 第10章
furthest = 第100章
```

---

## 13. 多设备阅读冲突

例子：

```text
手机读到100章
电脑旧Tab还停在60章
```

电脑晚一点发 heartbeat。

不能：

```text
电脑60章
覆盖
手机100章
```

需要：

```text
session leadership
+
revision
+
client/server timing
```

旧 Session 可继续贡献阅读统计，但不能无声覆盖最新 Resume Position。

---

## 14. 有效阅读

客户端不能说：

```text
“我阅读了8小时”
```

服务器根据：

```text
页面可见
滚动/翻页
文本量
阅读速度
idle
设备
行为模式
Risk
```

生成：

```text
Raw Reading Event
↓
Clean
↓
Risk
↓
Validated Reading Fact
```

只有 Validated Facts 用于：

- 作者数据
- 推荐
- 排行
- 会员池
- 免费阅读扶持池

---

## 15. 书架

支持：

```text
最近阅读
追更
完本
已购视觉聚合
稍后阅读
自定义分组
更新提醒
```

### 关键原则

```text
Bookshelf
History
Entitlement
```

三者互相独立。

用户：

```text
移出书架
```

不能：

```text
删除已购买章节
```

作品下架：

```text
书架仍存在
↓
显示“暂不可用”
```

---

## 16. 社区

统一 UGC 类型：

```text
BOOK_SHORT_REVIEW
BOOK_LONG_REVIEW
CHAPTER_COMMENT
PARAGRAPH_COMMENT
FAN_CIRCLE_POST
AUTHOR_POST
USER_POST
REPLY
```

### 评论规则

支持：

```text
回复
多级关系
UI扁平显示
点赞
@
作者回复
作者置顶
平台精选
```

作者不能因为差评删除正常评论。

### 段评

必须使用：

```text
paragraph_anchor_id
```

章节修订后：

```text
exact match
text match
position match
manual
```

迁移。

迁移失败：

> 保留历史，不得错误挂到新段落。

---

## 17. 作者动态

类型：

```text
更新通知
请假
加更
活动
完结
新书
普通动态
```

这属于社区公开内容。

作者责任编辑工作消息不是这里。

---

## 18. 书单

用户书单与官方书单分开。

```text
user_booklists
official_booklists
```

官方书单可以有明确人工排序：

```text
年度仙侠精选：
1 Book A
2 Book B
```

这是编辑策划，不是算法排行榜。

不能宣传成：

> 全站销量第一

除非 Ranking 数据真的支持。

---

## 19. 钱包

前端展示：

```text
总余额
充值币
赠币
流水
充值订单
退款
```

后端必须拆：

```text
RechargeCoin
GiftCoin
```

总余额只是显示投影。

### 资产批次

赠币：

```text
GiftCoinLot
origin
expires_at
available_amount
```

消费：

```text
最早过期
↓
FIFO
```

---

## 20. 充值

冻结：

```text
1 RMB = 100 RechargeCoin
```

例如活动：

```text
充100送20%
```

正确：

```text
支付 ¥100
→ 10000 RechargeCoin
→ 2000 GiftCoin
```

错误：

```text
支付 ¥100
→ 12000 RechargeCoin
```

### 充值前

必须实名认证。

### 支付模型

```text
PaymentOrder
↓
PaymentAttempt
↓
PaymentChannelEvent
↓
RechargeOrder
↓
Wallet credit
```

PaymentOrder 和 RechargeOrder 必须分开。

---

## 21. 退款 —— 必须保留的冻结案例

退款一定绑定具体：

```text
PaymentOrder
+
RechargeOrder
+
Asset Lots
+
Allocations
```

### 公式

```text
refundable cash
=
original paid cash
- consumed recharge coins from original order
- consumed promotional gift coins from original order
- naturally expired promotional gift coins from original order
- prior refunded amount
```

最低：

```text
0
```

### 退款成功后

回收：

```text
remaining recharge coins from source order
remaining active promotional gift coins from source order
```

其他来源 GiftCoin 不动。

### 冻结例子

```text
充值 ¥100
→ 10000 RechargeCoin
→ 2000 Promo GiftCoin

之后：
Gift已消费500
Gift自然过期1000
Gift有效剩余500
RechargeCoin全部剩余10000
```

最大普通退款：

```text
¥100
- ¥5 consumed gift
- ¥10 expired gift
=
¥85
```

退款成功：

```text
退现金 ¥85
回收 10000 RechargeCoin
回收 500 active GiftCoin
```

### 特别规则

若计算结果：

```text
<= 0
```

普通退款：

```text
不执行退款
不回收剩余资产
```

### 客服不能做

客服不能把系统计算的：

```text
¥65
```

手工改成：

```text
¥100
```

只能：

```text
解释
或
发起正式复核/例外审批
```

---

## 22. Chargeback

Chargeback ≠ Refund。

流程：

```text
Payment
↓
Chargeback
↓
Trace Lots
↓
Trace Consumption
↓
Trace Author Revenue
↓
Freeze/Recover
↓
Risk Case
```

如果作者收益已提现：

```text
future negative adjustment / recovery claim
```

普通用户钱包：

```text
不能直接变负数
```

债务进入：

```text
financial_recovery_claims
```

---

## 23. VIP购买

签约前：

```text
公开章节免费
```

作者不能自己：

```text
开启VIP
```

签约后由编辑/平台配置。

购买：

```text
单章
多章
当前到最新
完本全书
自动订阅
```

### 核心约束

```text
chapter_entitlements
UNIQUE(account_id, chapter_id)
```

### 不能做

不能：

```text
用户已经买过
↓
再次扣钱
```

---

## 24. 倒 V

以前免费不代表永久拥有。

倒 V 生效后：

```text
过去读过
但没购买
→ 重新阅读时需要VIP访问
```

但不能：

```text
自动追溯扣费
```

已经购买过的用户不能重复购买。

---

## 25. 会员

会员书库与 VIP 是两套事实。

例如：

```text
Chapter = VIP
Book = Member Library ACTIVE
```

会员：

```text
MEMBER_FREE
```

会员结束：

```text
重新 VIP_REQUIRED
```

但：

```text
Purchased entitlement
```

永久继续。

---

## 26. 礼物


# 微信小程序 API 安全审查 - 执行摘要

**审查日期**: 2026-07-16  
**审查人**: security-specialist agent  
**审查范围**: 微信小程序登录、会话管理、权限控制、多课题组隔离

---

## 🚨 关键发现

### 风险统计
- **P0 高危问题**: 3 个
- **P1 中危问题**: 11 个  
- **P2 低危问题**: 7 个

### 最严重的 3 个问题

1. **session_key 泄露 (P0)**
   - **位置**: `api_extensions.py:351`
   - **风险**: 微信 `session_key` 被返回给客户端，可被用于解密用户手机号等敏感信息
   - **影响**: 任何截获响应的攻击者（中间人、XSS）都可以解密用户数据

2. **缺少速率限制 (P0)**
   - **位置**: 所有 API 端点
   - **风险**: 登录接口可被暴力破解，邀请码可被枚举
   - **影响**: 服务器资源耗尽、账号泄露

3. **CSRF 保护不足 (P0)**
   - **位置**: 状态变更 API 端点
   - **风险**: 恶意网站可诱导用户执行非预期操作
   - **影响**: 用户被加入攻击者的课题组、数据被篡改

---

## 📋 完整风险清单

### P0 高危问题（需立即修复）

| 编号 | 问题 | 位置 | CWE | 复现路径 |
|------|------|------|-----|----------|
| P0-1 | session_key 泄露 | api_extensions.py:351 | CWE-200 | 截获登录响应 → 获取 session_key → 解密用户数据 |
| P0-2 | 缺少速率限制 | 所有 API 端点 | CWE-307 | 循环发送登录请求 → 暴力破解邀请码 |
| P0-3 | CSRF 保护不足 | 状态变更端点 | CWE-352 | 恶意网站发起跨站请求 → 修改用户数据 |

### P1 中危问题（近期修复）

| 编号 | 问题 | 位置 | 风险等级 |
|------|------|------|----------|
| P1-1 | 会话存储在内存 | api_extensions.py:145 | 重启丢失、无法分布式 |
| P1-2 | 输入验证不足 | 多个端点 | 可能导致 DoS 或数据污染 |
| P1-3 | 用户名冲突风险 | api_extensions.py:397 | OpenID 前缀重复导致冲突 |
| P1-4 | 文件操作缺锁 | api_extensions.py:150-177 | 并发写入数据丢失 |
| P1-5 | 配置验证缺失 | config.py:51-59 | 使用占位符配置启动服务 |
| P1-6 | 错误信息泄露 | api_extensions.py:263 | 可枚举有效用户 |
| P1-7 | 邀请码强度不足 | multilab_repository.py:92 | 6 字节熵可被暴力破解 |
| P1-8 | 会话固定攻击 | 会话管理逻辑 | 登录后未轮换 token |
| P1-9 | 缺少 HTTPS 强制 | config.py:57 | 明文传输敏感数据 |
| P1-10 | 缺少 Content-Type 验证 | API 处理逻辑 | 可能被用于 CSRF |
| P1-11 | 缺少请求大小限制 | API 处理逻辑 | DoS 风险 |

### P2 低危问题（后续优化）

| 编号 | 问题 | 建议优先级 |
|------|------|-----------|
| P2-1 | 错误信息泄露内部细节 | 低 |
| P2-2 | 缺少日志审计 | 中 |
| P2-3 | 缺少账号锁定 | 中 |
| P2-4 | 缺少会话数量限制 | 低 |
| P2-5 | Cookie 属性问题 | 低 |
| P2-6 | 缺少会话续期 | 低 |
| P2-7 | 缺少安全响应头 | 中 |

---

## 🛠️ 修复建议

### 立即行动（P0 修复）

1. **移除 session_key 返回**
   ```python
   # ❌ 修复前
   return {"session_key": wechat_session.session_key}
   
   # ✅ 修复后
   bind_token = self._pending_binds.create(...)
   return {"bind_token": bind_token}  # session_key 只存储在服务端
   ```

2. **实现速率限制**
   ```python
   # 每 IP 每分钟最多 10 次登录尝试
   if not self._login_limiter.check(client_ip):
       return {"error": "Too many requests"}
   ```

3. **添加 CSRF 验证**
   ```python
   # 所有状态变更操作验证 CSRF token
   if not self._verify_csrf_token(body, session_token):
       return {"error": "Invalid CSRF token"}
   ```

### 近期改进（P1 修复）

1. **迁移到 Redis 会话存储**（P1-1）
2. **添加输入长度和格式验证**（P1-2）
3. **使用哈希避免用户名冲突**（P1-3）
4. **添加文件操作锁**（P1-4）
5. **强制 HTTPS**（P1-9）

### 后续优化（P2 改进）

1. **添加审计日志**（P2-2）
2. **实现账号锁定机制**（P2-3）
3. **添加安全响应头**（P2-7）

---

## 📦 交付物

1. **安全审查报告**: `/docs/security-audit-report.md`
   - 完整的风险分析
   - 每个问题的攻击场景和修复代码
   - 验证步骤

2. **安全测试用例**: `/tests/test_security.py`
   - 21 个测试类，覆盖所有风险点
   - 包含单元测试和渗透测试脚本

3. **修复代码**: `/src/lab_literature_manager/security_fixes.py`
   - 可直接应用的修复代码
   - 包含速率限制器、输入验证器等工具类
   - 详细的应用步骤

---

## ✅ 验证步骤

### 自动化测试
```bash
# 运行安全测试套件
pytest tests/test_security.py -v

# 测试覆盖率
pytest tests/test_security.py --cov=src/lab_literature_manager --cov-report=html
```

### 手动渗透测试
```bash
# 1. 测试速率限制
for i in {1..15}; do
  curl -X POST http://localhost:8080/api/v1/wechat/miniprogram/login \
    -H "Content-Type: application/json" \
    -d '{"code": "test"}' &
done

# 2. 测试 CSRF 保护
curl -X POST http://localhost:8080/api/v1/wechat/bind \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"invite_code": "test"}' # 应返回 CSRF 错误

# 3. 测试输入验证
curl -X POST http://localhost:8080/api/v1/wechat/miniprogram/login \
  -d "{\"code\": \"$(python -c 'print("x"*200)')\"}" # 应拒绝
```

---

## 🎯 修复优先级时间表

| 阶段 | 时间 | 任务 |
|------|------|------|
| **紧急修复** | 1-2 天 | P0-1, P0-2, P0-3 |
| **重要改进** | 1 周 | P1-1, P1-2, P1-4, P1-9 |
| **持续优化** | 2-4 周 | P1 其余问题 + P2 高优先级 |
| **长期维护** | 持续 | P2 低优先级 + 安全监控 |

---

## 📞 后续支持

- 修复代码应用后，运行 `pytest tests/test_security.py` 验证
- 所有 P0 问题修复后，建议进行外部渗透测试
- 上线前完成 P0 和关键 P1 问题修复
- 定期审查（每季度）

---

## 参考资料

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [微信小程序登录安全指南](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)
- [CWE/SANS Top 25](https://cwe.mitre.org/top25/)

---

**审查状态**: ✅ 完成  
**交付时间**: 2026-07-16  
**下次审查建议**: P0 修复后立即复查

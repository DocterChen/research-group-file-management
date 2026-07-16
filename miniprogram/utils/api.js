// utils/api.js - API 请求封装
const app = getApp();

/**
 * 发起 API 请求
 * @param {string} url - 请求路径（相对路径，如 /wechat/miniprogram/login）
 * @param {object} options - 请求选项
 * @returns {Promise}
 */
function request(url, options = {}) {
  const {
    method = 'GET',
    data = {},
    needAuth = false,
    showLoading = false,
    loadingText = '加载中...'
  } = options;

  // 显示加载提示
  if (showLoading) {
    wx.showLoading({ title: loadingText, mask: true });
  }

  // 构建完整 URL
  const fullUrl = `${app.globalData.apiBase}${url}`;

  // 构建请求头
  const header = {
    'Content-Type': 'application/json'
  };

  // 如果需要认证，添加 session token
  if (needAuth && app.globalData.sessionToken) {
    header['Authorization'] = `Bearer ${app.globalData.sessionToken}`;
    header['X-Session-Token'] = app.globalData.sessionToken;
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: fullUrl,
      method,
      data,
      header,
      success(res) {
        if (showLoading) {
          wx.hideLoading();
        }

        // 检查 HTTP 状态码
        if (res.statusCode >= 200 && res.statusCode < 300) {
          // 检查业务错误
          if (res.data && res.data.error) {
            reject(new Error(res.data.error));
          } else {
            resolve(res.data);
          }
        } else if (res.statusCode === 401) {
          // 未授权，清除登录信息并跳转登录页
          app.clearLoginInfo();
          wx.reLaunch({ url: '/pages/login/login' });
          reject(new Error('登录已过期，请重新登录'));
        } else {
          reject(new Error(`请求失败：HTTP ${res.statusCode}`));
        }
      },
      fail(err) {
        if (showLoading) {
          wx.hideLoading();
        }
        console.error('请求失败:', err);
        reject(new Error('网络请求失败，请检查网络连接'));
      }
    });
  });
}

/**
 * GET 请求
 */
function get(url, options = {}) {
  return request(url, { ...options, method: 'GET' });
}

/**
 * POST 请求
 */
function post(url, data = {}, options = {}) {
  return request(url, { ...options, method: 'POST', data });
}

/**
 * PUT 请求
 */
function put(url, data = {}, options = {}) {
  return request(url, { ...options, method: 'PUT', data });
}

/**
 * DELETE 请求
 */
function del(url, options = {}) {
  return request(url, { ...options, method: 'DELETE' });
}

// ==================== 认证相关 API ====================

/**
 * 微信小程序登录
 * @param {string} code - wx.login() 返回的 code
 */
function wechatLogin(code) {
  return post('/wechat/miniprogram/login', { code }, { showLoading: true, loadingText: '登录中...' });
}

/**
 * 绑定课题组
 * @param {object} data - 绑定信息
 */
function bindLab(data) {
  return post('/wechat/bind', data, { showLoading: true, loadingText: '绑定中...' });
}

// ==================== 课题组相关 API ====================

/**
 * 获取课题组列表
 */
function getLabsList() {
  return get('/labs', { needAuth: true });
}

/**
 * 获取课题组信息
 * @param {string} labId
 */
function getLabInfo(labId) {
  return get(`/labs/${labId}`, { needAuth: true });
}

/**
 * 重新生成邀请码
 * @param {string} labId
 */
function regenerateInviteCode(labId) {
  return post(`/labs/${labId}/regenerate_invite_code`, {}, { needAuth: true });
}

// ==================== 成果相关 API ====================

/**
 * 获取成果列表
 * @param {object} params - 查询参数 { page, limit, search, type, status }
 */
function getOutputs(params = {}) {
  const queryString = Object.keys(params)
    .filter(key => params[key] !== undefined && params[key] !== '')
    .map(key => `${key}=${encodeURIComponent(params[key])}`)
    .join('&');

  const url = queryString ? `/outputs?${queryString}` : '/outputs';
  return get(url, { needAuth: true, showLoading: true });
}

/**
 * 获取成果详情
 * @param {string} outputId
 */
function getOutputDetail(outputId) {
  return get(`/outputs/${outputId}`, { needAuth: true, showLoading: true });
}

/**
 * 创建成果
 * @param {object} data
 */
function createOutput(data) {
  return post('/outputs', data, { needAuth: true, showLoading: true, loadingText: '创建中...' });
}

/**
 * 更新成果
 * @param {string} outputId
 * @param {object} data
 */
function updateOutput(outputId, data) {
  return put(`/outputs/${outputId}`, data, { needAuth: true, showLoading: true, loadingText: '保存中...' });
}

/**
 * 删除成果
 * @param {string} outputId
 */
function deleteOutput(outputId) {
  return del(`/outputs/${outputId}`, { needAuth: true, showLoading: true, loadingText: '删除中...' });
}

/**
 * 提交审核
 * @param {string} outputId
 */
function submitOutput(outputId) {
  return post(`/outputs/${outputId}/submit`, {}, { needAuth: true, showLoading: true, loadingText: '提交中...' });
}

/**
 * 审核通过
 * @param {string} outputId
 */
function approveOutput(outputId) {
  return post(`/outputs/${outputId}/approve`, {}, { needAuth: true, showLoading: true, loadingText: '审核中...' });
}

/**
 * 退回成果
 * @param {string} outputId
 * @param {string} reason
 */
function returnOutput(outputId, reason) {
  return post(`/outputs/${outputId}/return`, { reason }, { needAuth: true, showLoading: true, loadingText: '处理中...' });
}

/**
 * 归档成果
 * @param {string} outputId
 */
function archiveOutput(outputId) {
  return post(`/outputs/${outputId}/archive`, {}, { needAuth: true, showLoading: true, loadingText: '归档中...' });
}

// ==================== 仪表盘统计 API ====================

/**
 * 获取仪表盘统计数据
 */
function getDashboardStats() {
  return get('/dashboard/stats', { needAuth: true, showLoading: true });
}

// ==================== 成员相关 API ====================

/**
 * 获取成员列表
 */
function getMembers() {
  return get('/members', { needAuth: true });
}

/**
 * 创建成员
 * @param {object} data
 */
function createMember(data) {
  return post('/members', data, { needAuth: true, showLoading: true, loadingText: '创建中...' });
}

// ==================== 项目相关 API ====================

/**
 * 获取项目列表
 */
function getProjects() {
  return get('/projects', { needAuth: true });
}

/**
 * 创建项目
 * @param {object} data
 */
function createProject(data) {
  return post('/projects', data, { needAuth: true, showLoading: true, loadingText: '创建中...' });
}

module.exports = {
  request,
  get,
  post,
  put,
  del,
  // 认证
  wechatLogin,
  bindLab,
  // 课题组
  getLabsList,
  getLabInfo,
  regenerateInviteCode,
  // 成果
  getOutputs,
  getOutputDetail,
  createOutput,
  updateOutput,
  deleteOutput,
  submitOutput,
  approveOutput,
  returnOutput,
  archiveOutput,
  // 仪表盘
  getDashboardStats,
  // 成员
  getMembers,
  createMember,
  // 项目
  getProjects,
  createProject
};

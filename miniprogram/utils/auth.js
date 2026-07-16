// utils/auth.js - 认证工具函数
const app = getApp();

/**
 * 检查是否已登录
 * @returns {boolean}
 */
function isLoggedIn() {
  return app.isLoggedIn();
}

/**
 * 检查登录状态，未登录则跳转登录页
 * @returns {boolean}
 */
function requireLogin() {
  if (!isLoggedIn()) {
    wx.showToast({
      title: '请先登录',
      icon: 'none',
      duration: 2000
    });
    setTimeout(() => {
      wx.reLaunch({ url: '/pages/login/login' });
    }, 2000);
    return false;
  }
  return true;
}

/**
 * 退出登录
 */
function logout() {
  wx.showModal({
    title: '确认退出',
    content: '确定要退出登录吗？',
    success(res) {
      if (res.confirm) {
        app.clearLoginInfo();
        wx.reLaunch({ url: '/pages/login/login' });
      }
    }
  });
}

/**
 * 获取用户信息
 * @returns {object|null}
 */
function getUserInfo() {
  return app.globalData.userInfo;
}

/**
 * 获取课题组信息
 * @returns {object|null}
 */
function getLabInfo() {
  return app.globalData.labInfo;
}

/**
 * 检查用户角色
 * @param {string|string[]} roles - 角色或角色数组
 * @returns {boolean}
 */
function hasRole(roles) {
  const userInfo = getUserInfo();
  if (!userInfo) return false;

  const roleArray = Array.isArray(roles) ? roles : [roles];
  return roleArray.includes(userInfo.role);
}

/**
 * 检查是否是管理员
 * @returns {boolean}
 */
function isAdmin() {
  return hasRole(['admin', 'pi']);
}

/**
 * 格式化角色显示
 * @param {string} role
 * @returns {string}
 */
function formatRole(role) {
  const roleMap = {
    'pi': 'PI',
    'admin': '管理员',
    'member': '成员',
    'readonly': '只读'
  };
  return roleMap[role] || role;
}

module.exports = {
  isLoggedIn,
  requireLogin,
  logout,
  getUserInfo,
  getLabInfo,
  hasRole,
  isAdmin,
  formatRole
};

// pages/login/login.js
const api = require('../../utils/api');
const app = getApp();

Page({
  data: {
    logging: false
  },

  onLoad() {
    // 检查是否已登录
    if (app.isLoggedIn()) {
      wx.switchTab({ url: '/pages/dashboard/dashboard' });
    }
  },

  // 处理微信登录
  handleWechatLogin() {
    if (this.data.logging) return;

    this.setData({ logging: true });

    // 调用微信登录
    wx.login({
      success: (res) => {
        if (res.code) {
          this.loginWithCode(res.code);
        } else {
          this.showError('获取登录凭证失败');
        }
      },
      fail: (err) => {
        console.error('wx.login 失败:', err);
        this.showError('微信登录失败，请重试');
      }
    });
  },

  // 使用 code 登录
  async loginWithCode(code) {
    try {
      const result = await api.wechatLogin(code);

      if (result.status === 'success') {
        // 登录成功，保存信息并跳转仪表盘
        app.saveLoginInfo(result);
        wx.showToast({
          title: '登录成功',
          icon: 'success',
          duration: 1500
        });
        setTimeout(() => {
          wx.switchTab({ url: '/pages/dashboard/dashboard' });
        }, 1500);
      } else if (result.status === 'need_bind') {
        // 需要绑定课题组
        wx.navigateTo({
          url: `/pages/bind/bind?unionid=${result.unionid || ''}&openid=${result.openid}`
        });
      } else {
        this.showError('登录失败，请重试');
      }
    } catch (err) {
      console.error('登录失败:', err);
      this.showError(err.message || '登录失败，请检查网络连接');
    } finally {
      this.setData({ logging: false });
    }
  },

  // 显示错误提示
  showError(message) {
    this.setData({ logging: false });
    wx.showToast({
      title: message,
      icon: 'none',
      duration: 3000
    });
  }
});

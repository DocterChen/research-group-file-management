// app.js
App({
  globalData: {
    apiBase: 'http://localhost:8080/api/v1',
    sessionToken: '',
    csrfToken: '',
    userInfo: null,
    labInfo: null
  },

  onLaunch() {
    // 检查是否已登录
    const sessionToken = wx.getStorageSync('session_token');
    if (sessionToken) {
      this.globalData.sessionToken = sessionToken;
      this.globalData.csrfToken = wx.getStorageSync('csrf_token') || '';

      // 尝试加载用户信息
      const userInfo = wx.getStorageSync('user_info');
      const labInfo = wx.getStorageSync('lab_info');
      if (userInfo) this.globalData.userInfo = JSON.parse(userInfo);
      if (labInfo) this.globalData.labInfo = JSON.parse(labInfo);
    }
  },

  // 保存登录信息
  saveLoginInfo(data) {
    this.globalData.sessionToken = data.session_token;
    this.globalData.csrfToken = data.csrf_token || '';
    this.globalData.userInfo = {
      username: data.username,
      displayName: data.display_name,
      role: data.role
    };
    this.globalData.labInfo = {
      labId: data.lab_id,
      labName: data.lab_name
    };

    wx.setStorageSync('session_token', data.session_token);
    wx.setStorageSync('csrf_token', data.csrf_token || '');
    wx.setStorageSync('user_info', JSON.stringify(this.globalData.userInfo));
    wx.setStorageSync('lab_info', JSON.stringify(this.globalData.labInfo));
  },

  // 清除登录信息
  clearLoginInfo() {
    this.globalData.sessionToken = '';
    this.globalData.csrfToken = '';
    this.globalData.userInfo = null;
    this.globalData.labInfo = null;

    wx.removeStorageSync('session_token');
    wx.removeStorageSync('csrf_token');
    wx.removeStorageSync('user_info');
    wx.removeStorageSync('lab_info');
  },

  // 检查是否已登录
  isLoggedIn() {
    return !!this.globalData.sessionToken;
  }
});

// pages/profile/profile.js
const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    labInfo: null,
    inviteCode: '',
    isAdmin: false
  },

  onLoad() {
    if (!auth.requireLogin()) {
      return;
    }

    this.loadProfile();
  },

  onShow() {
    if (auth.isLoggedIn()) {
      this.loadProfile();
    }
  },

  // 加载个人信息
  async loadProfile() {
    const userInfo = auth.getUserInfo();
    const labInfo = auth.getLabInfo();
    const isAdmin = auth.isAdmin();

    this.setData({
      userInfo,
      labInfo,
      isAdmin
    });

    // 如果是管理员，加载邀请码
    if (isAdmin && labInfo) {
      this.loadInviteCode();
    }
  },

  // 加载邀请码
  async loadInviteCode() {
    try {
      const result = await api.getLabInfo(this.data.labInfo.labId);
      this.setData({
        inviteCode: result.invite_code
      });
    } catch (err) {
      console.error('加载邀请码失败:', err);
    }
  },

  // 复制邀请码
  handleCopyInviteCode() {
    if (!this.data.inviteCode) {
      wx.showToast({
        title: '邀请码未加载',
        icon: 'none'
      });
      return;
    }

    wx.setClipboardData({
      data: this.data.inviteCode,
      success: () => {
        wx.showToast({
          title: '邀请码已复制',
          icon: 'success'
        });
      }
    });
  },

  // 重新生成邀请码
  handleRegenerateInviteCode() {
    wx.showModal({
      title: '重新生成邀请码',
      content: '重新生成后，旧邀请码将失效。确定要继续吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            const result = await api.regenerateInviteCode(this.data.labInfo.labId);
            this.setData({
              inviteCode: result.invite_code
            });
            wx.showToast({
              title: '生成成功',
              icon: 'success'
            });
          } catch (err) {
            wx.showToast({
              title: err.message || '生成失败',
              icon: 'none'
            });
          }
        }
      }
    });
  },

  // 跳转到成果列表
  goToOutputs() {
    wx.switchTab({ url: '/pages/outputs/outputs' });
  },

  // 跳转到仪表盘
  goToDashboard() {
    wx.switchTab({ url: '/pages/dashboard/dashboard' });
  },

  // 退出登录
  handleLogout() {
    auth.logout();
  },

  // 格式化角色
  formatRole(role) {
    return auth.formatRole(role);
  }
});

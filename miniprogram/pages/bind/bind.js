// pages/bind/bind.js
const api = require('../../utils/api');
const app = getApp();

Page({
  data: {
    mode: 'join', // 'join' 或 'create'
    unionid: '',
    openid: '',
    displayName: '',
    inviteCode: '',
    labName: '',
    labSubtitle: '',
    submitting: false
  },

  onLoad(options) {
    // 从 URL 参数获取 unionid 和 openid
    this.setData({
      unionid: options.unionid || '',
      openid: options.openid || ''
    });

    if (!this.data.openid) {
      wx.showToast({
        title: '参数错误，请重新登录',
        icon: 'none',
        duration: 2000
      });
      setTimeout(() => {
        wx.reLaunch({ url: '/pages/login/login' });
      }, 2000);
    }
  },

  // 选择模式
  selectMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ mode });
  },

  // 输入昵称
  onDisplayNameInput(e) {
    this.setData({ displayName: e.detail.value });
  },

  // 输入邀请码
  onInviteCodeInput(e) {
    this.setData({ inviteCode: e.detail.value.toUpperCase() });
  },

  // 输入课题组名称
  onLabNameInput(e) {
    this.setData({ labName: e.detail.value });
  },

  // 输入课题组副标题
  onLabSubtitleInput(e) {
    this.setData({ labSubtitle: e.detail.value });
  },

  // 提交绑定
  async handleSubmit() {
    if (this.data.submitting) return;

    // 验证昵称
    if (!this.data.displayName.trim()) {
      wx.showToast({
        title: '请输入昵称',
        icon: 'none'
      });
      return;
    }

    // 验证不同模式的必填字段
    if (this.data.mode === 'join') {
      if (!this.data.inviteCode.trim()) {
        wx.showToast({
          title: '请输入邀请码',
          icon: 'none'
        });
        return;
      }
      if (this.data.inviteCode.length !== 6) {
        wx.showToast({
          title: '邀请码格式错误',
          icon: 'none'
        });
        return;
      }
    } else if (this.data.mode === 'create') {
      if (!this.data.labName.trim()) {
        wx.showToast({
          title: '请输入课题组名称',
          icon: 'none'
        });
        return;
      }
    }

    this.setData({ submitting: true });

    try {
      // 构建请求数据
      const requestData = {
        unionid: this.data.unionid,
        openid: this.data.openid,
        source: 'miniprogram',
        display_name: this.data.displayName.trim()
      };

      if (this.data.mode === 'join') {
        requestData.invite_code = this.data.inviteCode.trim();
      } else {
        requestData.create_lab = true;
        requestData.lab_name = this.data.labName.trim();
        requestData.lab_subtitle = this.data.labSubtitle.trim();
      }

      // 调用 API
      const result = await api.bindLab(requestData);

      if (result.status === 'success') {
        // 保存登录信息
        app.saveLoginInfo(result);

        wx.showToast({
          title: this.data.mode === 'join' ? '加入成功' : '创建成功',
          icon: 'success',
          duration: 1500
        });

        // 跳转仪表盘
        setTimeout(() => {
          wx.switchTab({ url: '/pages/dashboard/dashboard' });
        }, 1500);
      } else {
        throw new Error('绑定失败');
      }
    } catch (err) {
      console.error('绑定失败:', err);
      wx.showToast({
        title: err.message || '操作失败，请重试',
        icon: 'none',
        duration: 3000
      });
    } finally {
      this.setData({ submitting: false });
    }
  }
});

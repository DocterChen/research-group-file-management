// pages/dashboard/dashboard.js
const api = require('../../utils/api');
const auth = require('../../utils/auth');
const format = require('../../utils/format');

Page({
  data: {
    userInfo: null,
    labInfo: null,
    stats: {
      total: 0,
      approved: 0,
      submitted: 0,
      draft: 0
    },
    recentOutputs: [],
    loading: true
  },

  onLoad() {
    // 检查登录状态
    if (!auth.requireLogin()) {
      return;
    }

    this.loadDashboard();
  },

  onShow() {
    // 每次显示页面时刷新数据
    if (auth.isLoggedIn()) {
      this.loadDashboard();
    }
  },

  onPullDownRefresh() {
    this.loadDashboard();
  },

  // 加载仪表盘数据
  async loadDashboard() {
    this.setData({ loading: true });

    try {
      // 获取用户和课题组信息
      const userInfo = auth.getUserInfo();
      const labInfo = auth.getLabInfo();

      // 获取统计数据
      const statsResult = await api.getDashboardStats();

      // 获取最近成果（前5条）
      const outputsResult = await api.getOutputs({ limit: 5 });

      this.setData({
        userInfo,
        labInfo,
        stats: statsResult || this.data.stats,
        recentOutputs: outputsResult.outputs || [],
        loading: false
      });

      wx.stopPullDownRefresh();
    } catch (err) {
      console.error('加载仪表盘失败:', err);
      this.setData({ loading: false });
      wx.stopPullDownRefresh();

      wx.showToast({
        title: '加载失败',
        icon: 'none'
      });
    }
  },

  // 跳转到成果详情
  goToOutputDetail(e) {
    const outputId = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/output-detail/output-detail?id=${outputId}`
    });
  },

  // 跳转到成果列表
  goToOutputs() {
    wx.switchTab({ url: '/pages/outputs/outputs' });
  },

  // 格式化成果类型
  formatOutputType(type) {
    return format.formatOutputType(type);
  },

  // 格式化审核状态
  formatReviewStatus(status) {
    return format.formatReviewStatus(status);
  },

  // 获取状态样式类
  getStatusClass(status) {
    return format.getStatusClass(status);
  },

  // 格式化日期
  formatDateTime(datetime) {
    return format.formatRelativeTime(datetime);
  }
});

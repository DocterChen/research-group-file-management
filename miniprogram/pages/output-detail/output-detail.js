// pages/output-detail/output-detail.js
const api = require('../../utils/api');
const auth = require('../../utils/auth');
const format = require('../../utils/format');

Page({
  data: {
    outputId: '',
    output: null,
    loading: true,
    userInfo: null,
    canEdit: false,
    canReview: false
  },

  onLoad(options) {
    if (!auth.requireLogin()) {
      return;
    }

    const outputId = options.id;
    if (!outputId) {
      wx.showToast({
        title: '参数错误',
        icon: 'none'
      });
      setTimeout(() => {
        wx.navigateBack();
      }, 1500);
      return;
    }

    this.setData({
      outputId,
      userInfo: auth.getUserInfo()
    });

    this.loadOutput();
  },

  // 加载成果详情
  async loadOutput() {
    this.setData({ loading: true });

    try {
      const output = await api.getOutputDetail(this.data.outputId);

      // 判断权限
      const userInfo = this.data.userInfo;
      const canEdit = output.review_status === 'draft' || output.review_status === 'returned';
      const canReview = (userInfo.role === 'admin' || userInfo.role === 'pi') && output.review_status === 'submitted';

      this.setData({
        output,
        loading: false,
        canEdit,
        canReview
      });
    } catch (err) {
      console.error('加载成果详情失败:', err);
      this.setData({ loading: false });

      wx.showToast({
        title: '加载失败',
        icon: 'none'
      });
    }
  },

  // 提交审核
  async handleSubmit() {
    wx.showModal({
      title: '提交审核',
      content: '确定要提交审核吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await api.submitOutput(this.data.outputId);
            wx.showToast({
              title: '提交成功',
              icon: 'success'
            });
            this.loadOutput();
          } catch (err) {
            wx.showToast({
              title: err.message || '提交失败',
              icon: 'none'
            });
          }
        }
      }
    });
  },

  // 审核通过
  async handleApprove() {
    wx.showModal({
      title: '审核通过',
      content: '确定要通过这个成果吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await api.approveOutput(this.data.outputId);
            wx.showToast({
              title: '审核通过',
              icon: 'success'
            });
            this.loadOutput();
          } catch (err) {
            wx.showToast({
              title: err.message || '操作失败',
              icon: 'none'
            });
          }
        }
      }
    });
  },

  // 退回成果
  handleReturn() {
    wx.showModal({
      title: '退回成果',
      content: '请输入退回原因',
      editable: true,
      placeholderText: '请说明需要修改的内容',
      success: async (res) => {
        if (res.confirm) {
          const reason = res.content || '需要修改';
          try {
            await api.returnOutput(this.data.outputId, reason);
            wx.showToast({
              title: '已退回',
              icon: 'success'
            });
            this.loadOutput();
          } catch (err) {
            wx.showToast({
              title: err.message || '操作失败',
              icon: 'none'
            });
          }
        }
      }
    });
  },

  // 删除成果
  handleDelete() {
    wx.showModal({
      title: '删除成果',
      content: '确定要删除这个成果吗？删除后无法恢复。',
      confirmText: '删除',
      confirmColor: '#ef4444',
      success: async (res) => {
        if (res.confirm) {
          try {
            await api.deleteOutput(this.data.outputId);
            wx.showToast({
              title: '删除成功',
              icon: 'success'
            });
            setTimeout(() => {
              wx.navigateBack();
            }, 1500);
          } catch (err) {
            wx.showToast({
              title: err.message || '删除失败',
              icon: 'none'
            });
          }
        }
      }
    });
  },

  // 格式化函数
  formatOutputType(type) {
    return format.formatOutputType(type);
  },

  formatReviewStatus(status) {
    return format.formatReviewStatus(status);
  },

  getStatusClass(status) {
    return format.getStatusClass(status);
  },

  formatDateTime(datetime) {
    return format.formatDateTime(datetime, true);
  }
});

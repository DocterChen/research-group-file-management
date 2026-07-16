// pages/outputs/outputs.js
const api = require('../../utils/api');
const auth = require('../../utils/auth');
const format = require('../../utils/format');

Page({
  data: {
    outputs: [],
    loading: true,
    loadingMore: false,
    hasMore: true,
    page: 1,
    limit: 20,

    // 搜索和筛选
    searchKeyword: '',
    typeIndex: 0,
    statusIndex: 0,
    typeOptions: [
      { label: '全部类型', value: '' },
      { label: '论文', value: 'article' },
      { label: '专利', value: 'patent' },
      { label: '软件著作权', value: 'software_copyright' },
      { label: '会议成果', value: 'conference' },
      { label: '项目/基金材料', value: 'project_material' },
      { label: '数据与代码', value: 'dataset_code' }
    ],
    statusOptions: [
      { label: '全部状态', value: '' },
      { label: '草稿', value: 'draft' },
      { label: '待审核', value: 'submitted' },
      { label: '已退回', value: 'returned' },
      { label: '已通过', value: 'approved' },
      { label: '已归档', value: 'archived' }
    ]
  },

  onLoad() {
    if (!auth.requireLogin()) {
      return;
    }

    this.loadOutputs();
  },

  onPullDownRefresh() {
    this.setData({
      page: 1,
      outputs: [],
      hasMore: true
    });
    this.loadOutputs();
  },

  // 加载成果列表
  async loadOutputs() {
    if (this.data.loading) return;

    this.setData({ loading: true });

    try {
      const params = {
        page: this.data.page,
        limit: this.data.limit
      };

      // 添加搜索关键词
      if (this.data.searchKeyword) {
        params.search = this.data.searchKeyword;
      }

      // 添加类型筛选
      const selectedType = this.data.typeOptions[this.data.typeIndex].value;
      if (selectedType) {
        params.type = selectedType;
      }

      // 添加状态筛选
      const selectedStatus = this.data.statusOptions[this.data.statusIndex].value;
      if (selectedStatus) {
        params.status = selectedStatus;
      }

      const result = await api.getOutputs(params);

      this.setData({
        outputs: this.data.page === 1 ? result.outputs : [...this.data.outputs, ...result.outputs],
        hasMore: result.outputs.length >= this.data.limit,
        loading: false
      });

      wx.stopPullDownRefresh();
    } catch (err) {
      console.error('加载成果列表失败:', err);
      this.setData({ loading: false });
      wx.stopPullDownRefresh();

      wx.showToast({
        title: '加载失败',
        icon: 'none'
      });
    }
  },

  // 加载更多
  loadMore() {
    if (this.data.loadingMore || !this.data.hasMore) return;

    this.setData({
      page: this.data.page + 1,
      loadingMore: true
    });

    this.loadOutputs().finally(() => {
      this.setData({ loadingMore: false });
    });
  },

  // 搜索输入
  onSearchInput(e) {
    this.setData({ searchKeyword: e.detail.value });
  },

  // 执行搜索
  handleSearch() {
    this.setData({
      page: 1,
      outputs: [],
      hasMore: true
    });
    this.loadOutputs();
  },

  // 类型筛选变化
  onTypeChange(e) {
    this.setData({
      typeIndex: parseInt(e.detail.value),
      page: 1,
      outputs: [],
      hasMore: true
    });
    this.loadOutputs();
  },

  // 状态筛选变化
  onStatusChange(e) {
    this.setData({
      statusIndex: parseInt(e.detail.value),
      page: 1,
      outputs: [],
      hasMore: true
    });
    this.loadOutputs();
  },

  // 跳转到详情页
  goToDetail(e) {
    const outputId = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/output-detail/output-detail?id=${outputId}`
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
    return format.formatRelativeTime(datetime);
  },

  formatAuthors(authors) {
    return format.formatAuthors(authors, 3);
  }
});

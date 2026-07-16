// utils/format.js - 格式化工具函数

/**
 * 格式化成果类型
 * @param {string} type
 * @returns {string}
 */
function formatOutputType(type) {
  const typeMap = {
    'article': '论文',
    'patent': '专利',
    'software_copyright': '软件著作权',
    'conference': '会议成果',
    'project_material': '项目/基金材料',
    'dataset_code': '数据与代码'
  };
  return typeMap[type] || type;
}

/**
 * 格式化审核状态
 * @param {string} status
 * @returns {string}
 */
function formatReviewStatus(status) {
  const statusMap = {
    'draft': '草稿',
    'submitted': '待审核',
    'returned': '已退回',
    'approved': '已通过',
    'archived': '已归档'
  };
  return statusMap[status] || status;
}

/**
 * 获取状态标签样式类
 * @param {string} status
 * @returns {string}
 */
function getStatusClass(status) {
  const classMap = {
    'draft': 'tag-gray',
    'submitted': 'tag-warning',
    'returned': 'tag-danger',
    'approved': 'tag-success',
    'archived': 'tag-primary'
  };
  return classMap[status] || 'tag-gray';
}

/**
 * 格式化日期时间
 * @param {string} datetime - ISO 格式日期时间
 * @param {boolean} showTime - 是否显示时间
 * @returns {string}
 */
function formatDateTime(datetime, showTime = false) {
  if (!datetime) return '-';

  try {
    const date = new Date(datetime);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    if (showTime) {
      const hour = String(date.getHours()).padStart(2, '0');
      const minute = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day} ${hour}:${minute}`;
    }

    return `${year}-${month}-${day}`;
  } catch (e) {
    return datetime;
  }
}

/**
 * 格式化相对时间（多久之前）
 * @param {string} datetime
 * @returns {string}
 */
function formatRelativeTime(datetime) {
  if (!datetime) return '-';

  try {
    const date = new Date(datetime);
    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 7) {
      return formatDateTime(datetime);
    } else if (days > 0) {
      return `${days}天前`;
    } else if (hours > 0) {
      return `${hours}小时前`;
    } else if (minutes > 0) {
      return `${minutes}分钟前`;
    } else {
      return '刚刚';
    }
  } catch (e) {
    return datetime;
  }
}

/**
 * 截断文本
 * @param {string} text
 * @param {number} maxLength
 * @returns {string}
 */
function truncate(text, maxLength = 50) {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
}

/**
 * 格式化作者列表
 * @param {array} authors
 * @param {number} maxCount
 * @returns {string}
 */
function formatAuthors(authors, maxCount = 3) {
  if (!authors || authors.length === 0) return '-';

  if (authors.length <= maxCount) {
    return authors.join(', ');
  }

  return authors.slice(0, maxCount).join(', ') + ` 等${authors.length}人`;
}

/**
 * 高亮搜索关键词
 * @param {string} text
 * @param {string} keyword
 * @returns {string}
 */
function highlightKeyword(text, keyword) {
  if (!text || !keyword) return text;

  const regex = new RegExp(`(${keyword})`, 'gi');
  return text.replace(regex, '<span class="highlight">$1</span>');
}

module.exports = {
  formatOutputType,
  formatReviewStatus,
  getStatusClass,
  formatDateTime,
  formatRelativeTime,
  truncate,
  formatAuthors,
  highlightKeyword
};

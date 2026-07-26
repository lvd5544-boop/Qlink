export const APPLICATION_STATUS = {
  submitted: { text: '已申请', color: 'default' },
  viewed: { text: '招聘方已查看', color: 'processing' },
  needs_clarification: { text: '待补充说明', color: 'warning' },
  clarified: { text: '已提交说明', color: 'cyan' },
  clarification_closed: { text: '招聘方已关闭澄清', color: 'default' },
  interview_invited: { text: '已收到面试邀请', color: 'blue' },
  rejected: { text: '未进入后续流程', color: 'error' },
  accepted: { text: '已录用', color: 'success' },
};

export const EMPLOYER_APPLICATION_STATUS = {
  submitted: { text: '新申请', color: 'default' },
  viewed: { text: '已查看', color: 'processing' },
  needs_clarification: { text: '等待候选人说明', color: 'warning' },
  clarified: { text: '候选人已说明，待复核', color: 'cyan' },
  clarification_closed: { text: '已关闭，候选人未说明', color: 'default' },
  interview_invited: { text: '已发送面试邀请', color: 'blue' },
  rejected: { text: '已拒绝', color: 'error' },
  accepted: { text: '已录用', color: 'success' },
};

// 招聘方可通过通用状态下拉直接设置的状态。
// needs_clarification / clarified / interview_invited 只能由对应业务动作产生
// （发起澄清 / Claim 回复或人工关闭 / 面试邀请），不允许在此直设。
export const EMPLOYER_STATUS_OPTIONS = [
  { value: 'viewed', label: '招聘方已查看' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'accepted', label: '已录用' },
];

export const STATUS_FILTER_OPTIONS = [
  { value: '', label: '全部状态' },
  ...Object.entries(APPLICATION_STATUS).map(([value, cfg]) => ({
    value,
    label: cfg.text,
  })),
];

/** 招聘方申请记录页：澄清任务快捷筛选 */
export const CLARIFICATION_QUICK_FILTERS = [
  { value: '', label: '全部', statuses: null },
  { value: 'needs_clarification', label: '待澄清', statuses: ['needs_clarification'] },
  { value: 'clarified', label: '候选人已说明', statuses: ['clarified'] },
  { value: 'clarification_closed', label: '已关闭未说明', statuses: ['clarification_closed'] },
  { value: 'interview_invited', label: '面试邀请', statuses: ['interview_invited'] },
  { value: 'closed', label: '拒绝/录用', statuses: ['rejected', 'accepted'] },
];

export function getStatusConfig(status, audience = 'candidate') {
  const mapping = audience === 'employer' ? EMPLOYER_APPLICATION_STATUS : APPLICATION_STATUS;
  return mapping[status] || { text: status || '未知', color: 'default' };
}

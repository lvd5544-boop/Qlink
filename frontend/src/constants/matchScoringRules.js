/** 用户可理解的匹配说明。具体权重属于内部实现，不在产品界面展开。 */

const V2_CRITERIA = [
  { label: '方向是否一致', desc: '这份工作是否符合你明确选择的目标方向' },
  { label: '经历是否相关', desc: '已有工作、项目和行业经验能否支持申请' },
  { label: '关键要求是否体现', desc: '岗位看重的技能和成果是否已经写在简历里' },
  { label: '现实偏好是否合适', desc: '地点、薪资和工作方式是否符合你的选择' },
];

const V1_CRITERIA = [
  { label: '目标方向', desc: '你想做的工作是否和岗位一致' },
  { label: '相关经历', desc: '简历里的技能与经历能否支持申请' },
  { label: '基本条件', desc: '地点、经验和学历等信息是否需要进一步确认' },
];

export const SCORE_DISCLAIMER = '这是申请准备参考，不代表面试或录用结果。最终选择始终由你决定。';

export function getCurrentScoreRules(version = 2) {
  const criteria = version >= 2 ? V2_CRITERIA : V1_CRITERIA;
  return {
    title: '为什么会得到这个推荐？',
    intro: '系统主要参考以下信息，帮助你决定是否值得继续了解：',
    criteria,
    disclaimer: SCORE_DISCLAIMER,
  };
}

export function getPotentialScoreRules() {
  return {
    title: '“可提升空间”表示什么？',
    intro: '它用来比较不同准备方式，帮助你安排下一步。',
    points: [
      '现在就能改善的简历表达',
      '需要补充说明或真实材料的经历',
      '需要通过学习和实践逐步积累的能力',
    ],
    note: '它不是对个人潜力或录用机会的预测。',
    disclaimer: SCORE_DISCLAIMER,
  };
}

/** 评分规则说明（通俗语言，供用户点击「当前」「潜力」时查看） */

const V2_CRITERIA = [
  { label: '技能匹配', pct: 20, desc: '简历里的技能和岗位要求的技能有多吻合，包括技术栈、工具等' },
  { label: '工作经验', pct: 15, desc: '工作年限是否达到岗位要求，以及相关经历是否对口' },
  { label: '职位方向', pct: 20, desc: '你期望做的岗位和这份工作的方向是否一致；大类不符（如开发 vs 销售）会额外降分' },
  { label: '行业匹配', pct: 10, desc: '你过往所在的行业/领域，和岗位所在行业是否相关' },
  { label: '学历', pct: 5, desc: '学历是否达到岗位的最低要求' },
  { label: '工作地点', pct: 5, desc: '你的地点偏好和岗位工作地点是否契合（含远程）' },
  { label: '薪资期望', pct: 5, desc: '你的期望薪资和岗位给出的薪资范围是否接近' },
  { label: '项目影响力', pct: 10, desc: '过往项目有没有拿得出手的成果，比如数据提升、业务贡献等' },
  { label: '软实力', pct: 5, desc: '沟通协作、领导力等软性能力是否符合岗位描述' },
  { label: '成长潜力', pct: 10, desc: '学习能力、晋升空间等发展潜力' },
];

const V1_CRITERIA = [
  { label: '技能匹配', pct: 35, desc: '简历技能和岗位要求的重合程度' },
  { label: '职位方向', pct: 20, desc: '期望职位和岗位名称是否对口' },
  { label: '工作经验', pct: 15, desc: '工作年限是否满足岗位要求' },
  { label: '工作地点', pct: 5, desc: '地点偏好和岗位地点是否契合' },
  { label: '薪资期望', pct: 5, desc: '期望薪资和岗位薪资范围是否匹配' },
  { label: '学历', pct: 10, desc: '学历是否达到岗位要求' },
  { label: '软实力', pct: 10, desc: '沟通、协作等软性能力是否符合要求' },
];

export const SCORE_DISCLAIMER = '以上评分由 AI 根据简历和岗位信息自动计算，仅供参考，不代表实际录取结果。';

export function getCurrentScoreRules(version = 2) {
  const criteria = version === 2 ? V2_CRITERIA : V1_CRITERIA;
  return {
    title: '「当前」评分是怎么算的？',
    intro: '当前分反映的是你现在和这份岗位的匹配程度。系统会从以下几个角度综合打分，满分 10 分：',
    criteria,
    disclaimer: SCORE_DISCLAIMER,
  };
}

export function getPotentialScoreRules() {
  return {
    title: '「潜力」评分是怎么算的？',
    intro: '潜力分是一个参考值，表示如果你补齐岗位要求的缺失技能和软实力，综合得分大概能提升到多少。',
    points: [
      '以你当前的评分为基础',
      '假设你把岗位要求的缺失技能都补上',
      '假设软实力方面的差距也补齐',
      '其他条件（经验、学历、地点等）保持不变',
    ],
    note: '潜力分越高，说明通过针对性提升（比如学一门技能、补一段经历）后，匹配度改善空间越大。',
    disclaimer: SCORE_DISCLAIMER,
  };
}

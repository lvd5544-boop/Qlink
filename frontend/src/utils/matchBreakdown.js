/** 从 score_breakdown 提取分项（与后端 extract_breakdown_for_api 对齐） */

const SOFT_SKILL_NOISE = new Set([
  '任职要求', '岗位职责', '其他任务', '相关专业', '专业知识', '以上学历',
  '工作经验', '能力要求', '任职', '要求', '负责', '完成', '进行', '开展',
  '以及', '相关', '工作', '岗位', '人员', '条件', '优先', '熟悉', '具有',
  '具备', '良好', '以上', '以下', '本科', '硕士', '博士', '学历',
]);

export function filterSoftSkillsForDisplay(list) {
  return (list || []).filter((s) => s && !SOFT_SKILL_NOISE.has(s) && s.length >= 2);
}

const DIMENSION_LABELS_V1 = [
  ['skills', '技能匹配'],
  ['title', '职位方向'],
  ['experience', '工作经验'],
  ['location', '工作地点'],
  ['salary', '薪资期望'],
  ['education', '学历'],
  ['soft_skills', '软实力'],
];

const DIMENSION_LABELS_V2 = [
  ['skills', '技能匹配'],
  ['experience', '工作经验'],
  ['role_match', '职位方向'],
  ['industry_match', '行业匹配'],
  ['education', '学历'],
  ['location', '工作地点'],
  ['salary', '薪资期望'],
  ['impact', '项目影响力'],
  ['soft_skills', '软实力'],
  ['growth_potential', '成长潜力'],
];

const REASON_DIM_LABELS_V2 = {
  skills: '技能',
  role_match: '职位方向',
  industry_match: '行业',
  experience: '经验',
  impact: '项目影响力',
  growth_potential: '成长潜力',
};

const REASON_DIM_LABELS_V1 = {
  skills: '技能',
  title: '职位方向',
  experience: '经验',
  location: '地点',
  salary: '薪资',
  education: '学历',
  soft_skills: '软实力',
};

export function extractBreakdownFromScoreBreakdown(scoreBreakdown) {
  if (!scoreBreakdown || typeof scoreBreakdown !== 'object') return null;

  const version = scoreBreakdown.version ?? (scoreBreakdown.source === 'hybrid_v2' ? 2 : 1);
  const labels = version >= 2 ? DIMENSION_LABELS_V2 : DIMENSION_LABELS_V1;
  const dimensions = [];

  for (const [key, label] of labels) {
    const dim = scoreBreakdown[key];
    if (!dim || typeof dim !== 'object' || dim.weight == null) continue;
    dimensions.push({
      key,
      label,
      score: dim.score,
      ratio: dim.ratio ?? 0,
      weight: dim.weight,
      weight_pct: Math.round((dim.weight / 10) * 100),
    });
  }

  const skills = scoreBreakdown.skills || {};
  const soft = scoreBreakdown.soft_skills || {};

  return {
    version,
    dimensions,
    missing_skills: skills.missing || [],
    matched_skills: skills.matched || [],
    soft_skills_missing: filterSoftSkillsForDisplay(soft.missing),
  };
}

export function resolveMatchBreakdown(item) {
  if (item?.breakdown?.dimensions?.length) return item.breakdown;
  return extractBreakdownFromScoreBreakdown(item?.score_breakdown);
}

export function buildMatchReasonFromBreakdown(scoreBreakdown, score) {
  if (!scoreBreakdown) return null;

  const version = scoreBreakdown.version ?? (scoreBreakdown.source === 'hybrid_v2' ? 2 : 1);
  const dimLabels = version >= 2 ? REASON_DIM_LABELS_V2 : REASON_DIM_LABELS_V1;
  const parts = [];

  for (const [key, label] of Object.entries(dimLabels)) {
    const ratio = scoreBreakdown[key]?.ratio ?? 0;
    if (ratio >= 0.8) parts.push(`${label}匹配良好`);
    else if (ratio < 0.5) parts.push(`${label}偏弱`);
  }

  const missing = scoreBreakdown.skills?.missing || [];
  if (missing.length) parts.push(`简历中未找到 ${missing.slice(0, 3).join(', ')}，需确认`);

  if (!parts.length) return `综合匹配 ${score}/10`;
  return `综合 ${score}/10：` + parts.slice(0, 5).join('；');
}

export function resolveMatchReason(item) {
  const reason = item?.reason?.trim();
  if (reason && !reason.includes('快速评估')) return reason;
  return buildMatchReasonFromBreakdown(item?.score_breakdown, item?.score) || reason || '暂无匹配理由';
}

export function resolveMissingSkills(item, breakdown) {
  const bd = breakdown || resolveMatchBreakdown(item);
  return item?.missing_skills?.length
    ? item.missing_skills
    : bd?.missing_skills || item?.score_breakdown?.skills?.missing || [];
}

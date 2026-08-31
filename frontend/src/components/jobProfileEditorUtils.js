const joinList = (items = []) => items.filter(Boolean).join('\n');
const joinNames = (items = []) => items
  .map((item) => (typeof item === 'string' ? item : item?.name))
  .filter(Boolean)
  .join(', ');
const splitLines = (value = '') => value.split('\n').map((item) => item.trim()).filter(Boolean);
const splitComma = (value = '') => value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);

const requirementKey = (type, text) => `${type}::${String(text || '').trim().toLocaleLowerCase()}`;

const defaultClassification = (type) => {
  if (['skill', 'experience', 'education', 'other'].includes(type)) return 'preferred';
  return 'context';
};

export const buildRequirementChoices = (values = {}, previous = []) => {
  const previousMap = new Map(previous.map((item) => [item.key, item.classification]));
  const rows = [];
  const add = (type, text, label) => {
    const normalized = String(text || '').trim();
    if (!normalized) return;
    const key = requirementKey(type, normalized);
    if (rows.some((item) => item.key === key)) return;
    rows.push({
      key,
      type,
      text: normalized,
      label,
      classification: previousMap.get(key) || defaultClassification(type),
    });
  };

  splitLines(values.responsibilities).forEach((item) => add('task', item, '岗位职责'));
  splitComma(values.required_skills).forEach((item) => add('skill', item, '专业技能'));
  if (values.experience_years !== null && values.experience_years !== undefined) {
    add('experience', `${values.experience_years} 年相关经验`, '经验要求');
  }
  add('education', values.education_requirement || values.education, '学历要求');
  add('location', values.location, '工作地点');
  String(values.requirements || '')
    .split(/[\n；;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => add('other', item, '其他要求'));
  return rows;
};

export const decisionsFromProfile = (profile = {}) => (
  profile?.layers?.target_role?.requirements || []
).map((item) => ({
  key: requirementKey(item.type, item.text),
  type: item.type,
  text: item.text,
  label: item.type,
  classification: item.is_hard_constraint
    ? 'hard'
    : (item.level === 'context' ? 'context' : 'preferred'),
}));

export const confirmationPayload = (profile = {}, choices = []) => {
  const choiceMap = new Map(choices.map((item) => [item.key, item.classification]));
  return (profile?.layers?.target_role?.requirements || []).map((item) => ({
    requirement_id: item.id,
    classification: choiceMap.get(requirementKey(item.type, item.text))
      || defaultClassification(item.type),
  }));
};

export const jobToForm = (job = {}) => ({
  title: job.title || '',
  company_name: job.company_name || '',
  location: job.location || '',
  salary_range: job.salary_range || '',
  experience_years: job.experience_years ?? null,
  education: job.education || '',
  education_requirement: job.education_requirement || '',
  responsibilities: joinList(job.responsibilities),
  requirements: job.requirements || '',
  required_skills: joinNames(job.required_skills),
  soft_skills: joinNames(job.soft_skills),
  leadership_signals: joinNames(job.leadership_signals),
  communication_signals: joinNames(job.communication_signals),
  other_notes: /^parsed_by=/i.test(job.other_notes || '') ? '' : (job.other_notes || ''),
});

export const formToJob = (values, existing = {}) => {
  const existingJob = { ...existing };
  delete existingJob.job_id;
  delete existingJob.publication_status;
  delete existingJob.school_tier_keywords;
  return {
    ...existingJob,
    ...values,
    experience_years: values.experience_years ?? null,
    responsibilities: splitLines(values.responsibilities),
    required_skills: splitComma(values.required_skills).map((name) => ({
      name,
      level: existing.required_skills?.find((item) => item?.name === name)?.level || 'intermediate',
    })),
    soft_skills: splitComma(values.soft_skills),
    leadership_signals: splitComma(values.leadership_signals),
    communication_signals: splitComma(values.communication_signals),
  };
};

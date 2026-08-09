const MAX_ITEM_LENGTH = 90;

export function truncatePreparationText(value, limit = MAX_ITEM_LENGTH) {
  const text = String(value || '').trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
}

function uniqueText(items, limit) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const text = truncatePreparationText(item);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
    if (result.length >= limit) break;
  }
  return result;
}

function recommendedStrategy(issue) {
  return (issue?.strategies || []).find((item) => item.recommended)
    || issue?.strategies?.[0]
    || null;
}

export function buildOpportunityPreparation({ jobTitle, requirements = [], claims = [], diagnostic = {} }) {
  const safeClaims = claims.filter(
    (claim) => claim?.current_text && claim.evidence_state !== 'conflict_detected',
  );
  const confirmedClaims = safeClaims.filter(
    (claim) => claim.evidence_state === 'supported_by_user_evidence'
      || claim.confirmation_state === 'user_confirmed',
  );
  const pendingClaims = safeClaims.filter((claim) => !confirmedClaims.includes(claim));
  const issues = diagnostic?.issues || [];
  const clarificationIssues = issues.filter(
    (issue) => issue.route_state === 'clarify' || issue.route_state === 'unknown',
  );
  const unresolvedIssues = issues.filter(
    (issue) => ['constraint', 'develop', 'unknown'].includes(issue.route_state),
  );
  const developmentIssue = issues.find((issue) => issue.route_state === 'develop');
  const developmentStrategy = recommendedStrategy(developmentIssue);

  return {
    jobTitle: jobTitle || '未命名岗位',
    availableNow: confirmedClaims.slice(0, 3).map((claim) => ({
      text: truncatePreparationText(claim.current_text),
      source: claim.source_locator,
      evidenceState: claim.evidence_state,
    })),
    interviewStories: confirmedClaims.slice(0, 2).map((claim) => ({
      anchor: truncatePreparationText(claim.current_text),
      fields: [
        '情境：当时的背景和约束是什么？',
        '任务：你具体负责什么？',
        '行动：你亲自做了什么，为什么？',
        '结果：哪些结果或证据可以核对？',
      ],
    })),
    clarifyingQuestions: uniqueText([
      ...clarificationIssues.map((issue) => issue.diagnosis),
      ...pendingClaims.map((claim) => `请确认这条经历的角色、行动和结果：${claim.current_text}`),
    ], 3),
    developmentAction: developmentStrategy ? {
      title: truncatePreparationText(developmentStrategy.title || developmentIssue?.diagnosis),
      detail: truncatePreparationText(developmentStrategy.next_action || developmentIssue?.diagnosis),
    } : null,
    unresolvedRequirements: uniqueText([
      ...unresolvedIssues.map((issue) => issue.diagnosis),
      ...requirements.map((item) => `待逐条确认：${item?.text || item}`),
    ], 3),
  };
}

export function opportunityPreparationAsText(preparation) {
  const lines = [
    `目标岗位：${preparation.jobTitle}`,
    '',
    '一、现在可用',
    ...preparation.availableNow.map((item) => `- ${item.text}`),
    '',
    '二、面试故事',
    ...preparation.interviewStories.flatMap((story, index) => [
      `${index + 1}. ${story.anchor}`,
      ...story.fields.map((field) => `   - ${field}`),
    ]),
    '',
    '三、待说清',
    ...preparation.clarifyingQuestions.map((item) => `- ${item}`),
    '',
    '四、一个行动',
    ...(preparation.developmentAction
      ? [`- ${preparation.developmentAction.title}：${preparation.developmentAction.detail}`]
      : ['- 当前没有经用户确认的发展行动。']),
    '',
    '五、未解决要求',
    ...preparation.unresolvedRequirements.map((item) => `- ${item}`),
    '',
    '说明：本卡只整理当前岗位 JD、你已确认或已提供证据的经历，以及待确认事项；不会补写未知事实。',
  ];
  return lines.join('\n');
}

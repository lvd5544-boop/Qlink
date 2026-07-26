/** 从澄清请求正文或结构化字段提取 claim 文本 */
export function extractClaimText(source) {
  if (!source) return '';
  if (source.claim_text) return source.claim_text;
  const body = source.body || '';
  const match = body.match(/关于 claim：「(.+?)」/);
  return match ? match[1] : '';
}

export function resumeRewriteLink(resumeId, claimText) {
  const base = resumeId ? `/candidate/my-resumes?resumeId=${resumeId}` : '/candidate/my-resumes';
  if (!claimText) return base;
  return `${base}&claimHint=${encodeURIComponent(claimText.slice(0, 120))}`;
}

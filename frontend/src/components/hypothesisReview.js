export function replaceHypothesisStatus(diagnostic, hypothesisId, nextHypothesis) {
  if (!diagnostic) return diagnostic;
  const updateIssue = (issue) => ({
    ...issue,
    hypotheses: (issue.hypotheses || []).map((item) => (
      String(item.id) === String(hypothesisId) ? { ...item, ...nextHypothesis } : item
    )),
  });
  const issues = (diagnostic.issues || []).map(updateIssue);
  const categories = Object.fromEntries(
    Object.entries(diagnostic.categories || {}).map(([key, rows]) => [
      key,
      (rows || []).map(updateIssue),
    ]),
  );
  return { ...diagnostic, issues, categories };
}

/**
 * Requirement readiness is decided by the backend diagnostic (`issue.route_state`).
 * The client only buckets what it is told: an issue the client cannot place
 * degrades to `unknown` rather than to a verdict about the candidate.
 */
export const ROUTE_STATES = ['ready', 'clarify', 'develop', 'constraint', 'unknown'];

export function routeStateOf(issue) {
  const state = issue?.route_state;
  return ROUTE_STATES.includes(state) ? state : 'unknown';
}

export function groupIssuesByRouteState(issues = []) {
  const grouped = Object.fromEntries(ROUTE_STATES.map((key) => [key, []]));
  for (const issue of issues) grouped[routeStateOf(issue)].push(issue);
  return grouped;
}

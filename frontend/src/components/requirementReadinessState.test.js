import assert from 'node:assert/strict';
import test from 'node:test';

import { ROUTE_STATES, groupIssuesByRouteState, routeStateOf } from './requirementReadinessState.js';

test('the five route states stay stable and ordered', () => {
  assert.deepEqual(ROUTE_STATES, ['ready', 'clarify', 'develop', 'constraint', 'unknown']);
});

test('a capability issue is never routed to develop by the client', () => {
  const issue = { id: 'i1', category: 'capability', claim_ids: [], strategies: [] };
  assert.equal(routeStateOf(issue), 'unknown');
  assert.notEqual(routeStateOf(issue), 'develop');
});

test('the backend route state wins over any client-side category guess', () => {
  assert.equal(routeStateOf({ category: 'capability', route_state: 'clarify' }), 'clarify');
  assert.equal(routeStateOf({ category: 'expression', route_state: 'develop' }), 'develop');
  assert.equal(routeStateOf({ category: 'hard_constraint', route_state: 'constraint' }), 'constraint');
});

test('an unrecognised or missing route state degrades to unknown, not to a verdict', () => {
  assert.equal(routeStateOf({ route_state: 'not_a_state' }), 'unknown');
  assert.equal(routeStateOf({}), 'unknown');
  assert.equal(routeStateOf(undefined), 'unknown');
});

test('grouping keeps every issue and never invents a develop entry', () => {
  const issues = [
    { id: 'a', route_state: 'ready' },
    { id: 'b', route_state: 'clarify' },
    { id: 'c', category: 'capability' },
    { id: 'd', route_state: 'constraint' },
  ];
  const grouped = groupIssuesByRouteState(issues);

  assert.deepEqual(Object.keys(grouped), ROUTE_STATES);
  assert.deepEqual(grouped.ready.map((item) => item.id), ['a']);
  assert.deepEqual(grouped.clarify.map((item) => item.id), ['b']);
  assert.deepEqual(grouped.develop, []);
  assert.deepEqual(grouped.constraint.map((item) => item.id), ['d']);
  assert.deepEqual(grouped.unknown.map((item) => item.id), ['c']);
  assert.equal(
    Object.values(grouped).reduce((total, list) => total + list.length, 0),
    issues.length,
  );
});

test('grouping tolerates an empty or missing issue list', () => {
  assert.deepEqual(groupIssuesByRouteState([]).develop, []);
  assert.deepEqual(groupIssuesByRouteState().unknown, []);
});

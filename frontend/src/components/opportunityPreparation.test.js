import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildOpportunityPreparation,
  opportunityPreparationAsText,
} from './opportunityPreparation.js';

test('opportunity preparation enforces the five short-card limits and evidence boundary', () => {
  const claims = Array.from({ length: 8 }, (_, index) => ({
    current_text: `真实经历 ${index} ${'x'.repeat(120)}`,
    source_locator: `experience.${index}`,
    evidence_state: index === 7 ? 'conflict_detected' : 'supported_by_user_evidence',
    confirmation_state: 'user_confirmed',
  }));
  const issues = Array.from({ length: 6 }, (_, index) => ({
    route_state: index === 0 ? 'develop' : 'unknown',
    diagnosis: `待确认要求 ${index}`,
    strategies: index === 0 ? [{ recommended: true, title: '建立作品证据', next_action: '完成一个可核对的小任务' }] : [],
  }));

  const result = buildOpportunityPreparation({ jobTitle: '数据工程师', claims, diagnostic: { issues } });

  assert.equal(result.availableNow.length, 3);
  assert.equal(result.interviewStories.length, 2);
  assert.equal(result.clarifyingQuestions.length, 3);
  assert.equal(result.unresolvedRequirements.length, 3);
  assert.ok(result.availableNow.every((item) => item.text.length <= 90));
  assert.equal(result.developmentAction.title, '建立作品证据');
  assert.doesNotMatch(opportunityPreparationAsText(result), /录用概率|自动投递/);
});

test('unconfirmed claims become clarification prompts, never ready-to-use material', () => {
  const result = buildOpportunityPreparation({
    claims: [{
      current_text: '可能负责过一次数据迁移',
      evidence_state: 'candidate_asserted',
      confirmation_state: 'pending',
    }],
  });

  assert.deepEqual(result.availableNow, []);
  assert.match(result.clarifyingQuestions[0], /请确认/);
});

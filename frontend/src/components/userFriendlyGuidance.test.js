import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const readSource = (relativePath) =>
  readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('candidate guidance does not expose internal scoring mechanics', () => {
  const scoringRules = readSource('../constants/matchScoringRules.js')
  const scoringPopover = readSource('./ScoreRulesPopover.jsx')
  const simulationPanel = readSource('./ImprovementSimulationPanel.jsx')
  const helpPage = readSource('../pages/Help.jsx')

  assert.doesNotMatch(scoringRules, /\bpct\s*:/)
  assert.doesNotMatch(scoringPopover, /c\.pct|约\s*\{?.*%/)
  assert.doesNotMatch(simulationPanel, /potential_score|marginal_delta|toFixed\(2\)/)
  assert.doesNotMatch(helpPage, /Wilson|置信区间|0\s*[–-]\s*10\s*分/)
})

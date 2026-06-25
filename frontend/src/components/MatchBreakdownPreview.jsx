import { Progress, Space, Tag, Typography } from 'antd';
import { resolveMatchBreakdown, resolveMissingSkills, filterSoftSkillsForDisplay } from '../utils/matchBreakdown';

const { Text } = Typography;

function scoreColor(ratio) {
  if (ratio >= 0.8) return '#10b981';
  if (ratio >= 0.5) return '#f59e0b';
  return '#ef4444';
}

/** 列表项内的紧凑分项预览 */
export default function MatchBreakdownPreview({
  item,
  breakdown,
  scoreBreakdown,
  missingSkills,
  compact = false,
}) {
  const resolved = breakdown?.dimensions?.length
    ? breakdown
    : resolveMatchBreakdown({ breakdown, score_breakdown: scoreBreakdown, ...item });

  const dimensions = resolved?.dimensions || [];
  const missing = resolveMissingSkills(
    { missing_skills: missingSkills, score_breakdown: scoreBreakdown, ...item },
    resolved,
  );
  const softMissing = filterSoftSkillsForDisplay(
    resolved?.soft_skills_missing
      || item?.score_breakdown?.soft_skills?.missing
      || [],
  );

  if (!dimensions.length && !missing.length && !softMissing.length) return null;

  if (compact) {
    return (
      <div style={{ marginTop: 8 }}>
        {dimensions.length > 0 && (
          <Space size={[4, 4]} wrap>
            {dimensions.map((d) => (
              <Tag
                key={d.key}
                style={{
                  margin: 0,
                  fontSize: 12,
                  borderColor: scoreColor(d.ratio ?? 0),
                  color: scoreColor(d.ratio ?? 0),
                  background: '#fff',
                }}
              >
                {d.label} {Math.round((d.ratio ?? 0) * 100)}%
              </Tag>
            ))}
          </Space>
        )}
        {missing.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>缺技能：</Text>
            <Space size={[4, 4]} wrap>
              {missing.slice(0, 6).map((sk) => (
                <Tag key={sk} color="red" style={{ margin: 0, fontSize: 12 }}>
                  {sk}
                </Tag>
              ))}
              {missing.length > 6 && (
                <Text type="secondary" style={{ fontSize: 11 }}>+{missing.length - 6}</Text>
              )}
            </Space>
          </div>
        )}
        {dimensions.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>软实力差距：</Text>
            {softMissing.length > 0 ? (
              <Space size={[4, 4]} wrap style={{ marginTop: 4 }}>
                {softMissing.slice(0, 4).map((sk) => (
                  <Tag key={sk} color="orange" style={{ margin: 0, fontSize: 12 }}>
                    {sk}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>暂无</Text>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8, marginTop: 8 }}>
      {dimensions.map((d) => (
        <div key={d.key}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <Text style={{ fontSize: 12 }}>{d.label}</Text>
            <Text type="secondary" style={{ fontSize: 11 }}>{Math.round((d.ratio ?? 0) * 100)}%</Text>
          </div>
          <Progress
            percent={Math.round((d.ratio ?? 0) * 100)}
            strokeColor={scoreColor(d.ratio ?? 0)}
            size="small"
            showInfo={false}
          />
        </div>
      ))}
    </div>
  );
}

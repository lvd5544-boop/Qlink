import { Empty, Space, Tag, Typography } from 'antd';

const { Text } = Typography;

const TYPE_META = {
  experience: { label: '经历', color: '#6455d9', tint: '#f1efff' },
  project: { label: '项目', color: '#0f9187', tint: '#eafaf7' },
  claim: { label: '关键事实', color: '#0f9187', tint: '#eafaf7' },
  artifact: { label: '支撑材料', color: '#c87816', tint: '#fff6e8' },
  evidence: { label: '支撑材料', color: '#c87816', tint: '#fff6e8' },
  capability: { label: '能力', color: '#d63c86', tint: '#fff0f7' },
  requirement: { label: '岗位要求', color: '#2f61cf', tint: '#eef4ff' },
  resume_version: { label: '简历版本', color: '#64748b', tint: '#f1f5f9' },
};

const VIEW_COPY = {
  unified: '经历是主线，能力与关键细节从经历中生长；材料和岗位只作为辅助连接。',
  timeline: '以完整经历为主线；日期只是经历上下文，具体事实收在经历详情中。',
  capability: '能力由项目或经历支撑。点击项目查看其中的具体事实与材料。',
  evidence: '这里只展示已建立的 Claim ↔ Evidence 关系；线条表示支持、相关或待澄清，不表示认证。',
  job: '从岗位明确要求回看相关经历与材料；未写出不等于不具备。',
};

function short(value, length = 28) {
  const text = String(value || '');
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function claimIdForNode(node) {
  return node.meta?.claim_id
    || (node.type === 'claim' ? String(node.id).replace('claim:', '') : null);
}

function nodeDetail(node, meta) {
  if (node.type === 'capability') return node.meta?.status || '由经历体现';
  if (node.type === 'requirement') {
    return node.meta?.status === 'evidence_found'
      ? `已找到 ${node.meta?.matched_claim_count || 0} 条相关经历`
      : '简历中暂未定位，建议澄清';
  }
  if (node.type === 'claim') return '点击查看或继续补充';
  if (node.meta?.detail_count) return `${node.meta.detail_count} 条关键细节`;
  return meta.label;
}

function columnLayout(nodes, view) {
  if (view === 'unified') {
    const lanes = [
      ['experience', 'project', 'resume_version'],
      ['capability', 'claim'],
      ['requirement', 'evidence', 'artifact'],
    ];
    const xPositions = [180, 520, 860];
    const positioned = [];
    lanes.forEach((types, laneIndex) => {
      const laneNodes = nodes.filter((node) => types.includes(node.type));
      laneNodes.forEach((node, index) => {
        positioned.push({
          ...node,
          x: xPositions[laneIndex],
          y: 132 + index * 104,
        });
      });
    });
    return positioned;
  }
  const lanes = view === 'capability'
    ? [['capability'], ['project', 'experience']]
    : view === 'evidence'
      ? [['claim'], ['evidence', 'artifact']]
      : view === 'job'
        ? [['requirement'], ['claim', 'project', 'experience'], ['evidence', 'artifact']]
        : [['experience', 'project', 'resume_version']];
  const xPositions = lanes.length === 1
    ? [520]
    : lanes.length === 2
      ? [270, 770]
      : [175, 520, 865];
  const positioned = [];
  lanes.forEach((types, laneIndex) => {
    const laneNodes = nodes.filter((node) => types.includes(node.type));
    laneNodes.forEach((node, index) => {
      positioned.push({
        ...node,
        x: xPositions[laneIndex],
        y: 92 + index * 112,
      });
    });
  });
  const included = new Set(positioned.map((node) => node.id));
  nodes.filter((node) => !included.has(node.id)).forEach((node, index) => {
    positioned.push({ ...node, x: 520, y: 92 + index * 112 });
  });
  return positioned;
}

function NodeCard({ node, onOpen }) {
  const meta = TYPE_META[node.type] || TYPE_META.claim;
  const claimId = claimIdForNode(node);
  const canOpen = Boolean(claimId);
  const detail = nodeDetail(node, meta);
  return (
    <g
      transform={`translate(${node.x - 138}, ${node.y - 38})`}
      onClick={() => canOpen && onOpen?.(claimId)}
      className={canOpen ? 'career-node career-node-clickable' : 'career-node'}
      role={canOpen ? 'button' : undefined}
      tabIndex={canOpen ? 0 : undefined}
      onKeyDown={(event) => {
        if (canOpen && (event.key === 'Enter' || event.key === ' ')) onOpen?.(claimId);
      }}
    >
      <rect width="276" height="76" rx="18" fill="#fff" stroke={meta.color} strokeOpacity=".3" />
      <rect width="7" height="76" rx="4" fill={meta.color} />
      <circle cx="31" cy="27" r="12" fill={meta.tint} stroke={meta.color} strokeWidth="2" />
      <circle cx="31" cy="27" r="4" fill={meta.color} />
      <text x="53" y="27" fontSize="15" fontWeight="700" fill="#172033">
        {short(node.label)}
      </text>
      <text x="53" y="50" fontSize="11" fill={meta.color}>
        {short(detail, 32)}
      </text>
    </g>
  );
}

function MobileNode({ node, onOpen }) {
  const meta = TYPE_META[node.type] || TYPE_META.claim;
  const claimId = claimIdForNode(node);
  return (
    <button
      type="button"
      className="career-mobile-node"
      style={{ '--node-color': meta.color, '--node-tint': meta.tint }}
      disabled={!claimId}
      onClick={() => claimId && onOpen?.(claimId)}
    >
      <span className="career-mobile-node-dot" />
      <span>
        <strong>{short(node.label, 38)}</strong>
        <small>{nodeDetail(node, meta)}</small>
      </span>
    </button>
  );
}

export default function CareerGraph({ value, view, onSelectClaim }) {
  const nodes = (value?.nodes || []).slice(0, view === 'unified' ? 30 : 18);
  if (!nodes.length) {
    const description = view === 'evidence'
      ? '还没有 Claim 与支撑材料的关系。请先在 Evidence Vault 中上传材料并关联到具体事实。'
      : view === 'capability'
        ? '还没有可归一化的能力。请先在简历中补充技能，并把技能关联到项目经历。'
        : '还没有可展示的职业记忆节点';
    return <Empty description={description} />;
  }

  const positioned = columnLayout(nodes, view);
  const byId = new Map(positioned.map((node) => [node.id, node]));
  const edges = (value.edges || []).map((edge) => ({
    ...edge,
    sourceNode: byId.get(edge.source),
    targetNode: byId.get(edge.target),
  })).filter((edge) => edge.sourceNode && edge.targetNode);
  const maxY = Math.max(...positioned.map((node) => node.y), 420);
  const height = Math.max(500, maxY + 82);
  const visibleTypes = [...new Set(positioned.map((node) => node.type))];
  const counts = positioned.reduce((result, node) => {
    result[node.type] = (result[node.type] || 0) + 1;
    return result;
  }, {});
  const countLabel = view === 'job'
    ? `${counts.requirement || 0} 项岗位要求 · ${counts.claim || 0} 条相关经历 · ${counts.evidence || counts.artifact || 0} 份材料`
    : view === 'unified'
      ? `${(counts.experience || 0) + (counts.project || 0)} 段经历 · ${counts.capability || 0} 项能力 · ${counts.claim || 0} 个关键细节`
      : `${nodes.length} 个关系节点`;

  return (
    <div className={`career-graph career-graph-${view}`}>
      <div className="career-graph-head">
        <Space wrap>
          {visibleTypes.map((type) => {
            const meta = TYPE_META[type] || TYPE_META.claim;
            return <Tag key={type} color={meta.color}>{meta.label}</Tag>;
          })}
        </Space>
        <Text type="secondary">{countLabel}</Text>
      </div>
      {view === 'unified' && (
        <div className="career-graph-mobile" aria-label="职业成长关系图">
          {[
            ['经历主线', ['experience', 'project', 'resume_version']],
            ['能力与细节', ['capability', 'claim']],
            ['材料与岗位', ['requirement', 'evidence', 'artifact']],
          ].map(([label, types], index) => {
            const laneNodes = nodes.filter((node) => types.includes(node.type));
            return (
              <section key={label} className="career-mobile-lane">
                {index > 0 && <div className="career-mobile-arrow">↓</div>}
                <Text strong>{label}</Text>
                <div className="career-mobile-node-list">
                  {laneNodes.length ? laneNodes.slice(0, 8).map((node) => (
                    <MobileNode key={node.id} node={node} onOpen={onSelectClaim} />
                  )) : <Text type="secondary">还没有相关内容</Text>}
                </div>
              </section>
            );
          })}
        </div>
      )}
      <svg viewBox={`0 0 1040 ${height}`} role="img" aria-label="职业档案关系图">
        <defs>
          <linearGradient id={`career-canvas-${view}`} x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#fbfaff" />
            <stop offset="52%" stopColor="#f4fbfa" />
            <stop offset="100%" stopColor="#fffaf2" />
          </linearGradient>
          <marker id="career-arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#a7b1c2" />
          </marker>
        </defs>
        <rect width="1040" height={height} rx="28" fill={`url(#career-canvas-${view})`} />
        {view === 'unified' && (
          <>
            <text x="180" y="62" textAnchor="middle" fontSize="13" fontWeight="700" fill="#5f52c7">经历主线</text>
            <text x="520" y="62" textAnchor="middle" fontSize="13" fontWeight="700" fill="#b62f74">能力与细节</text>
            <text x="860" y="62" textAnchor="middle" fontSize="13" fontWeight="700" fill="#ad6818">材料与岗位</text>
            <path d={`M 180 78 L 180 ${height - 28}`} stroke="#6455d9" strokeOpacity=".12" strokeWidth="18" strokeLinecap="round" />
            <circle cx="180" cy="78" r="7" fill="#6455d9" fillOpacity=".72" />
          </>
        )}
        {edges.map((edge) => (
          <g key={edge.id}>
            <path
              d={(() => {
                const toRight = edge.targetNode.x >= edge.sourceNode.x;
                const startX = edge.sourceNode.x + (toRight ? 138 : -138);
                const endX = edge.targetNode.x + (toRight ? -146 : 146);
                const middleX = (startX + endX) / 2;
                return `M ${startX} ${edge.sourceNode.y} C ${middleX} ${edge.sourceNode.y}, ${middleX} ${edge.targetNode.y}, ${endX} ${edge.targetNode.y}`;
              })()}
              fill="none"
              stroke={view === 'unified' ? '#9a8fd8' : '#a7b1c2'}
              strokeWidth={view === 'unified' ? '2.4' : '2'}
              strokeOpacity={view === 'unified' ? '.48' : '.72'}
              markerEnd="url(#career-arrow)"
            />
            <title>{edge.relationship || '相关'}</title>
          </g>
        ))}
        {positioned.map((node) => (
          <NodeCard key={node.id} node={node} onOpen={onSelectClaim} />
        ))}
      </svg>
      <Text type="secondary" className="career-graph-caption">{VIEW_COPY[view]}</Text>
    </div>
  );
}

import { Card, Typography, Divider, Collapse } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

const { Title, Paragraph } = Typography;
const { Panel } = Collapse;

export default function Help() {
  const role = localStorage.getItem('role') || 'candidate';

  const candidateHelp = (
    <>
      <Title level={3}>求职者帮助中心</Title>
      <Paragraph>快连 QLink 为您提供一站式智能求职服务。以下是常见问题与操作指南。</Paragraph>
      <Divider />
      <Collapse accordion>
        <Panel header="如何上传简历？" key="1">
          <Paragraph>进入「上传简历」页面，点击“选择文件并上传”，支持 PDF / Word / TXT 格式。上传后 AI 自动解析并生成结构化画像。</Paragraph>
        </Panel>
        <Panel header="AI 虚拟面试官怎么使用？" key="2">
          <Paragraph>在「虚拟面试」页面，点击“开始面试”按钮，AI 面试官会引导多轮对话并给出建议。面试观察或系统推测不会自动写入简历；只有你明确确认的内容才能成为个人事实。</Paragraph>
        </Panel>
        <Panel header="岗位推荐是如何生成的？" key="3">
          <Paragraph>系统基于您的简历画像（技能、地点、薪资期望等）与平台所有岗位进行智能匹配，按匹配度排序展示。点击“刷新匹配”可获取最新结果。</Paragraph>
        </Panel>
        <Panel header="如何管理我的简历？" key="4">
          <Paragraph>在「我的简历」页面可查看、编辑、删除已上传的简历。编辑功能支持修改姓名、技能、工作经历等所有字段。</Paragraph>
        </Panel>
        <Panel header="浏览岗位和搜索" key="5">
          <Paragraph>「浏览岗位」页面展示平台所有公开岗位（含权威平台抓取岗位）。您可通过关键字、地点、薪资范围进行筛选，点击岗位卡片查看详细信息。</Paragraph>
        </Panel>
        <Panel header="数据分析与简历诊断" key="6">
          <Paragraph>「数据分析」会整理公开岗位和公开职业经验，帮助你了解同类岗位通常看重什么。它只提供准备方向，不代表任何公司的录用标准。</Paragraph>
        </Panel>
        <Panel header="如何参加试用、提交反馈或删除数据？" key="7">
          <Paragraph>进入「更多 → 试用与反馈」。你可以分别管理产品研究、汇总指标和模型改进授权，随时退出 pilot，也可以通过明确的二次确认永久删除账号及其关联私有数据。</Paragraph>
        </Panel>
      </Collapse>
    </>
  );

  const employerHelp = (
    <>
      <Title level={3}>招聘方帮助中心</Title>
      <Paragraph>欢迎使用快连 QLink 招聘管理平台，高效连接优质人才。</Paragraph>
      <Divider />
      <Collapse accordion>
        <Panel header="如何发布新岗位？" key="1">
          <Paragraph>进入「发布岗位」页面，上传 JD 文件或直接粘贴岗位描述，AI 将自动解析并结构化存储。发布后立即可被求职者搜索和匹配。</Paragraph>
        </Panel>
        <Panel header="如何管理我的岗位？" key="2">
          <Paragraph>在「我的岗位」页面可查看、编辑、删除已发布的岗位。点击“查看”可预览详情，“编辑”修改信息，“删除”将移除岗位及其相关匹配记录。</Paragraph>
        </Panel>
        <Panel header="如何查看匹配的候选人？" key="3">
          <Paragraph>在「我的岗位」列表中，点击某个岗位的“候选人”按钮，即可看到系统根据技能、地点等维度为您推荐的最匹配求职者，并支持在线查看简历详情。</Paragraph>
        </Panel>
        <Panel header="候选人推荐依据是什么？" key="4">
          <Paragraph>系统会整理岗位要求与候选人已提供的经历，帮助招聘方找到值得进一步查看的人选。推荐仅用于辅助阅读，不能代替人工判断或直接淘汰候选人。</Paragraph>
        </Panel>
        <Panel header="如何联系候选人？" key="5">
          <Paragraph>当前版本支持查看候选人的联系方式（若简历中包含）。未来将推出在线邀请、面试安排等一站式功能，敬请期待。</Paragraph>
        </Panel>
      </Collapse>
    </>
  );

  return (
    <Card
      className="content-card"
      title={<span><QuestionCircleOutlined /> 帮助中心</span>}
    >
      {role === 'candidate' ? candidateHelp : employerHelp}
    </Card>
  );
}

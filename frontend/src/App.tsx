import { useState } from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  DashboardOutlined, DatabaseOutlined, RadarChartOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import Dashboard from './pages/Dashboard';
import CorpusExplorer from './pages/CorpusExplorer';
import BrandRadar from './pages/BrandRadar';
import Compliance from './pages/Compliance';

const { Header, Sider, Content } = Layout;

const PAGES: Record<string, () => JSX.Element> = {
  dashboard: Dashboard,
  corpus: CorpusExplorer,
  brands: BrandRadar,
  compliance: Compliance,
};

export default function App() {
  const [page, setPage] = useState(
    () => new URLSearchParams(window.location.search).get('page') || 'dashboard',
  );   // 支持 ?page=corpus 深链（演示/截图用）
  const Page = PAGES[page] ?? Dashboard;
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" collapsible>
        <div style={{ color: '#fff', textAlign: 'center', padding: 16, fontWeight: 700 }}>
          GreenSilk-Monitor
          <div style={{ fontSize: 11, fontWeight: 400, color: '#9ca3af' }}>破壁中东 · v0.5</div>
        </div>
        <Menu
          theme="dark" mode="inline" selectedKeys={[page]} onClick={e => setPage(e.key)}
          items={[
            { key: 'dashboard', icon: <DashboardOutlined />, label: '舆情大屏' },
            { key: 'corpus', icon: <DatabaseOutlined />, label: '语料库检索' },
            { key: 'brands', icon: <RadarChartOutlined />, label: '品牌声量' },
            { key: 'compliance', icon: <SafetyCertificateOutlined />, label: '文化合规审查' },
          ]}
        />
      </Sider>
      <Layout>
        <Content style={{ padding: 20 }}>
          <Typography.Title level={4} style={{ marginTop: 0 }}>
            {page === 'dashboard' && '舆情监测大屏'}
            {page === 'corpus' && '中阿英可比语料库检索（KWIC）'}
            {page === 'brands' && '品牌声量对比看板'}
            {page === 'compliance' && '跨文化传播合规审查台'}
          </Typography.Title>
          <Page />
        </Content>
      </Layout>
    </Layout>
  );
}

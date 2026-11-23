import { useEffect, useState } from 'react';
import { Card, Spin, Table, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import { getBrandVolume, BrandVolume } from '../api';

export default function BrandRadar() {
  const [brands, setBrands] = useState<BrandVolume[] | null>(null);

  useEffect(() => { getBrandVolume().then(r => setBrands(r.brands)); }, []);

  if (!brands) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;

  const barOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['阿语', '英语', '中文'] },
    xAxis: { type: 'category', data: brands.map(b => b.brand_id) },
    yAxis: { type: 'value', name: '语料声量' },
    series: [
      { name: '阿语', type: 'bar', stack: 'v', data: brands.map(b => b.ar), itemStyle: { color: '#52c41a' } },
      { name: '英语', type: 'bar', stack: 'v', data: brands.map(b => b.en), itemStyle: { color: '#1677ff' } },
      { name: '中文', type: 'bar', stack: 'v', data: brands.map(b => b.zh), itemStyle: { color: '#f5222d' } },
    ],
  };

  const cnBrands = new Set(brands.filter(b => b.group === 'cn').map(b => b.brand_id));
  const compBrands = new Set(brands.filter(b => b.group === 'comp').map(b => b.brand_id));
  const top = brands.slice(0, 8);
  const maxTotal = Math.max(...brands.map(b => b.total), 1);

  const radarOption = {
    tooltip: {},
    legend: { data: ['中国品牌集群', '西方/日韩对照'], bottom: 0 },
    radar: {
      indicator: top.map(b => ({ name: b.brand_id, max: maxTotal })),
    },
    series: [{
      type: 'radar',
      data: [
        { value: top.map(b => (cnBrands.has(b.brand_id) ? b.total : 0)),
          name: '中国品牌集群', itemStyle: { color: '#0f7a4d' } },
        { value: top.map(b => (compBrands.has(b.brand_id) ? b.total : 0)),
          name: '西方/日韩对照', itemStyle: { color: '#1677ff' } },
      ],
    }],
  };

  return (
    <>
      <Card title="品牌声量堆叠图（阿/英/中 语言分布）" style={{ marginBottom: 16 }}>
        <ReactECharts option={barOption} height={360} />
      </Card>
      <Card title="中国品牌集群 vs 对照品牌（双层舆论场对照雷达）" style={{ marginBottom: 16 }}>
        <ReactECharts option={radarOption} height={360} />
      </Card>
      <Card title="明细数据">
        <Table rowKey="brand_id" size="small" dataSource={brands}
          columns={[
            { title: '品牌', dataIndex: 'name' },
            { title: '分组', dataIndex: 'group', render: (g: string) =>
              g === 'cn' ? <Tag color="green">中国品牌</Tag> : <Tag color="blue">对照品牌</Tag> },
            { title: '阿语', dataIndex: 'ar' },
            { title: '英语', dataIndex: 'en' },
            { title: '中文', dataIndex: 'zh' },
            { title: '合计', dataIndex: 'total' },
          ]} />
      </Card>
    </>
  );
}

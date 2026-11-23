import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Spin, Alert } from 'antd';
import ReactECharts from 'echarts-for-react';
import { getOverview, Overview } from '../api';

const LANG_LABEL: Record<string, string> = { ar: '阿拉伯语', en: '英语', zh: '中文' };
const VARIANT_LABEL: Record<string, string> = {
  MSA: '标准阿语', Khaliji: '海湾方言', Arabizi: '阿语拉丁混写', EN: '英语', ZH: '中文',
};

export default function Dashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [tl, setTl] = useState<{ timeline: { ym: string; n: number }[]; phases: any[] } | null>(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    getOverview().then(setData).catch(e => setErr(String(e)));
    fetch('/api/v1/stats/timeline').then(r => r.json()).then(setTl).catch(() => {});
  }, []);

  if (err) return <Alert type="error" message="后端未启动或语料库为空" description={err} />;
  if (!data) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;

  const langPie = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['38%', '65%'],
      data: data.by_language.map(x => ({
        name: LANG_LABEL[x.language] ?? x.language, value: x.n,
      })),
    }],
  };

  const countryBar = {
    tooltip: {},
    xAxis: { type: 'category', data: data.by_country.map(x => x.country) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: data.by_country.map(x => x.n), itemStyle: { color: '#0f7a4d' } }],
  };

  const variantBar = {
    tooltip: {},
    xAxis: { type: 'category', data: data.by_lang_variant.map(x => VARIANT_LABEL[x.lang_variant] ?? x.lang_variant) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: data.by_lang_variant.map(x => x.n) }],
  };

  const PHASE_COLORS = ['rgba(15,122,77,0.10)', 'rgba(22,119,255,0.10)', 'rgba(245,34,45,0.10)', 'rgba(250,140,22,0.10)'];
  const timelineOption = tl && tl.timeline.length ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: tl.timeline.map(t => t.ym) },
    yAxis: { type: 'value', name: '月度语料量' },
    series: [{
      type: 'line', smooth: true, areaStyle: { opacity: 0.25 },
      data: tl.timeline.map(t => t.n), itemStyle: { color: '#0f7a4d' },
      markArea: {
        itemStyle: { opacity: 0.6 },
        data: (tl.phases ?? []).map((p: any, i: number) => [
          { xAxis: p.range[0], itemStyle: { color: PHASE_COLORS[i % 4] },
            label: { show: true, formatter: p.name, position: 'insideTopLeft' } },
          { xAxis: p.range[1] },
        ]),
      },
    }],
  } : null;

  return (
    <>
      <Row gutter={[16, 16]}>
        <Col span={6}><Card><Statistic title="语料总篇数" value={data.total_docs} /></Card></Col>
        <Col span={6}><Card><Statistic title="UGC 评论" value={data.total_ugc} /></Card></Col>
        <Col span={6}><Card><Statistic title="总词数" value={data.total_words} /></Card></Col>
        <Col span={6}><Card><Statistic title="阿语占比" value={(data.arabic_ratio * 100).toFixed(1) + '%'} suffix="" /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={8}>
          <Card title="语言分布（门禁：阿语 ≥45%）">
            <ReactECharts option={langPie} height={280} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="国家分布（GCC 核心圈）">
            <ReactECharts option={countryBar} height={280} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="语种变体（MSA / 海湾方言 / Arabizi）">
            <ReactECharts option={variantBar} height={280} />
          </Card>
        </Col>
      </Row>
      {timelineOption && (
        <Row style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card title="历时演化时间线（四阶段事件锚点：萌芽 → 破局 → 爆发 → 深水）">
              <ReactECharts option={timelineOption} height={320} />
            </Card>
          </Col>
        </Row>
      )}
    </>
  );
}

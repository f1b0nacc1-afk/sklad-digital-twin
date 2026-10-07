import { useQuery } from '@tanstack/react-query'
import { Card, Col, Descriptions, Empty, Row, Select, Space, Spin, Statistic, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { Twin, Warehouse } from '../api/types'
import WarehouseCanvas, { type Selection } from '../components/plan/WarehouseCanvas'

const STATUS_TAG = {
  active: <Tag color="green">на месте</Tag>,
  missing: <Tag color="orange">не найден</Tag>,
  removed: <Tag>убран</Tag>,
}

function SelectionCard({ selection, twin }: { selection: Selection | null; twin: Twin }) {
  const cellById = useMemo(() => new Map(twin.cells.map((c) => [c.id, c])), [twin])
  if (!selection) {
    return <Empty description="Выберите объект, стеллаж или ячейку на плане" />
  }
  if (selection.kind === 'object') {
    const o = selection.object
    return (
      <Descriptions column={1} size="small" title={o.name || `Объект №${o.id}`}>
        <Descriptions.Item label="ID">{o.id}</Descriptions.Item>
        <Descriptions.Item label="Класс">{o.type_code}</Descriptions.Item>
        <Descriptions.Item label="Статус">{STATUS_TAG[o.status]}</Descriptions.Item>
        <Descriptions.Item label="Ячейка">
          {o.cell_id ? cellById.get(o.cell_id)?.address : 'вне адресного хранения'}
        </Descriptions.Item>
        <Descriptions.Item label="Координаты, м">
          {o.x_m?.toFixed(2)}; {o.y_m?.toFixed(2)}
        </Descriptions.Item>
        <Descriptions.Item label="Последнее подтверждение">
          {new Date(o.last_seen_at).toLocaleString('ru-RU')}
        </Descriptions.Item>
      </Descriptions>
    )
  }
  if (selection.kind === 'shelf') {
    const s = selection.shelf
    const cells = twin.cells.filter((c) => c.shelf_id === s.id)
    const occupied = cells.filter((c) => twin.occupied_cell_ids.includes(c.id)).length
    return (
      <Descriptions column={1} size="small" title={`Стеллаж ${s.code}`}>
        <Descriptions.Item label="Габариты, м">
          {s.width_m} × {s.depth_m} × {s.height_m}
        </Descriptions.Item>
        <Descriptions.Item label="Ярусы × места">
          {s.levels} × {s.places_per_level}
        </Descriptions.Item>
        <Descriptions.Item label="Занято ячеек">
          {occupied} из {cells.length}
        </Descriptions.Item>
      </Descriptions>
    )
  }
  const c = selection.cell
  return (
    <Descriptions column={1} size="small" title={`Ячейка ${c.address}`}>
      <Descriptions.Item label="Тип">{c.shelf_id ? 'стеллажная' : 'напольная'}</Descriptions.Item>
      {c.level && <Descriptions.Item label="Ярус (видимый)">{c.level}</Descriptions.Item>}
      <Descriptions.Item label="Состояние">
        {selection.occupied ? <Tag color="red">занята</Tag> : <Tag color="green">свободна</Tag>}
      </Descriptions.Item>
    </Descriptions>
  )
}

export default function TwinPage() {
  const warehouses = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => api<Warehouse[]>('/api/warehouses'),
  })
  const [warehouseId, setWarehouseId] = useState<number | null>(null)
  const currentId = warehouseId ?? warehouses.data?.[0]?.id ?? null
  const [selection, setSelection] = useState<Selection | null>(null)

  const twin = useQuery({
    queryKey: ['twin', currentId],
    queryFn: () => api<Twin>(`/api/warehouses/${currentId}/twin`),
    enabled: currentId != null,
  })

  if (warehouses.isLoading) return <Spin />
  if (!warehouses.data?.length) {
    return <Empty description="Склады не созданы. Запустите scripts/seed_demo.py или создайте склад." />
  }

  const t = twin.data
  const occupancy = t && t.cells.length ? (100 * t.occupied_cell_ids.length) / t.cells.length : 0

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Цифровой двойник
        </Typography.Title>
        <Select
          style={{ minWidth: 260 }}
          value={currentId}
          onChange={(id) => {
            setWarehouseId(id)
            setSelection(null)
          }}
          options={warehouses.data.map((w) => ({ value: w.id, label: w.name }))}
        />
      </Space>
      {t && (
        <Row gutter={16}>
          <Col span={6}><Card size="small"><Statistic title="Объектов на складе" value={t.objects.filter((o) => o.status === 'active').length} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="Не найдено" value={t.objects.filter((o) => o.status === 'missing').length} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="Занятость ячеек" value={occupancy} precision={1} suffix="%" /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="Стеллажей / ячеек" value={`${t.shelves.length} / ${t.cells.length}`} /></Card></Col>
        </Row>
      )}
      <Row gutter={16}>
        <Col flex="auto">
          <Card size="small" styles={{ body: { padding: 0, height: 560 } }}>
            {t ? <WarehouseCanvas twin={t} selected={selection} onSelect={setSelection} /> : <Spin />}
          </Card>
        </Col>
        <Col flex="320px">
          <Card size="small" title="Карточка" style={{ height: '100%' }}>
            {t && <SelectionCard selection={selection} twin={t} />}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

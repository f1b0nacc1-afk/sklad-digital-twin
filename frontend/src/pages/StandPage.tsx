import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { type ReactNode, useState } from 'react'
import { api } from '../api/client'
import type { StandDetectionRow, StandRun, StandRunListItem, StandScene } from '../api/stand'
import AuthImage from '../components/AuthImage'

const LIGHTING: Record<string, string> = {
  even: 'равномерный',
  dim: 'тусклый',
  side: 'боковой, длинные тени',
  bright: 'яркий',
}
const CLASS_LABEL: Record<string, string> = {
  box: 'коробка',
  pallet: 'паллета',
  container: 'контейнер',
  person: 'человек',
}
const pct = (v: number) => `${(v * 100).toFixed(1)} %`

function fileUrl(run: string, path: string) {
  return `/api/stand/runs/${run}/files/${path}`
}

function EvaluationTab({ run }: { run: StandRun }) {
  const ev = run.evaluation
  if (!ev) return <Empty description="Нет отчёта испытания. Запустите python -m cv.sim.evaluate" />
  const loc = ev.localization
  const ok = (v: boolean) => (v ? <Tag color="green">выполнено</Tag> : <Tag color="red">не выполнено</Tag>)
  const det = Object.entries(ev.detection).map(([cls, v]) => ({ cls, ...v }))

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message={`Испытание на ${ev.scenes} кадрах 20 Мп, которых модель не видела: другая установка камеры, другая погрешность фокусного расстояния, 4 режима света.`}
        description="Данные синтетические: на реальной камере точность детекции будет ниже, геометрия (калибровка и привязка) переносится без изменений."
      />
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Card size="small"><Statistic title="mAP@0.5 (тест)" value={ev.map?.map50 ?? 0} precision={3} suffix="≥ 0,85" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small">
            <Statistic title="Верная ячейка: модель камеры" value={loc.camera_model.cell_accuracy * 100} precision={1} suffix="%" valueStyle={{ color: '#3f8600' }} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small">
            <Statistic title="Верная ячейка: гомография пола (по ТЗ)" value={loc.floor_homography.cell_accuracy * 100} precision={1} suffix="%" valueStyle={{ color: loc.floor_homography.cell_accuracy >= 0.9 ? '#3f8600' : '#cf1322' }} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small"><Statistic title="Время на кадр (GPU)" value={ev.timing_ms.mean} precision={0} suffix="мс, ≤ 3000" /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="Детекция по классам (IoU ≥ 0,5)">
            <Table
              size="small"
              pagination={false}
              rowKey="cls"
              dataSource={det}
              columns={[
                { title: 'Класс', dataIndex: 'cls', render: (c: string) => CLASS_LABEL[c] ?? c },
                { title: 'Precision', dataIndex: 'precision', render: pct },
                { title: 'Recall', dataIndex: 'recall', render: pct },
                { title: 'Найдено', dataIndex: 'tp' },
                { title: 'Ложных', dataIndex: 'fp' },
                { title: 'Пропущено', dataIndex: 'fn' },
              ]}
            />
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              Ошибка подсчёта: {ev.count_mae?.toFixed(2)} на кадр (≤ 1 на 20). Средняя уверенность верных детекций: {ev.mean_confidence_tp?.toFixed(3)}.
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="Привязка к ячейкам (НФТ-К-04: ≥ 90 %)">
            <Table
              size="small"
              pagination={false}
              rowKey="name"
              dataSource={[
                { name: 'Гомография пола (как в ТЗ)', ...loc.floor_homography },
                { name: 'Модель камеры + высоты полок', ...loc.camera_model },
              ]}
              columns={[
                { title: 'Метод', dataIndex: 'name' },
                { title: 'Ячейка', dataIndex: 'cell_accuracy', render: pct },
                { title: 'RMSE', dataIndex: 'rmse_cm', render: (v: number) => `${v.toFixed(2)} см` },
                { title: '95 %', dataIndex: 'p95_cm', render: (v: number) => `${v.toFixed(2)} см` },
                { title: 'На полках', dataIndex: 'shelf_rmse_cm', render: (v: number) => `${v.toFixed(2)} см` },
                { title: 'ТЗ', key: 'ok', render: (_: unknown, r: { name: string; cell_accuracy: number }) => ok(r.cell_accuracy >= 0.9) },
              ]}
            />
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              Верх стеллажа ближе к камере, чем пол: плоская гомография сдвигает объекты на полках от центра кадра на 3–7 см (параллакс). Модель камеры пересекает луч с плоскостью полки.
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card size="small" title="Калибровка по меткам">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Невязка по меткам">{ev.calibration.marker_fit_rmse_cm.toFixed(3)} см</Descriptions.Item>
              <Descriptions.Item label="Контрольные точки пола">
                {ev.calibration.floor_control_points.camera_model_cm.toFixed(2)} см (≤ 1 см)
              </Descriptions.Item>
              <Descriptions.Item label="Верх стеллажей, гомография">
                <Typography.Text type="danger">{ev.calibration.shelf_top_points.homography_cm.toFixed(2)} см</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Верх стеллажей, модель камеры">
                {ev.calibration.shelf_top_points.camera_model_cm.toFixed(2)} см
              </Descriptions.Item>
              <Descriptions.Item label="Высота камеры (истина / оценка)">
                {ev.camera.height_true_m.toFixed(3)} / {ev.camera.height_estimated_m.toFixed(3)} м
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title="Контроль качества кадра (Т-17)">
            <Descriptions column={1} size="small">
              {Object.entries(ev.quality_checks).map(([name, q]) => (
                <Descriptions.Item key={name} label={{ normal: 'Нормальный', black: 'Чёрный', overexposed: 'Пересвет', defocused: 'Расфокус' }[name] ?? name}>
                  {q.ok ? <Tag color="green">принят</Tag> : <Tag color="orange">отбракован</Tag>}
                  {q.sharpness !== undefined && <Typography.Text type="secondary">резкость {q.sharpness}</Typography.Text>}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title="Человек в кадре (Т-19)">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Кадров с человеком">{ev.people.with_person}</Descriptions.Item>
              <Descriptions.Item label="Отбраковано (> 20 % кадра)">{ev.people.rejected}</Descriptions.Item>
              <Descriptions.Item label="Принято частично">{ev.people.accepted_partial}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

const STATUS: Record<StandDetectionRow['status'], ReactNode> = {
  ok: <Tag color="green">верно</Tag>,
  wrong_cell: <Tag color="orange">не та ячейка</Tag>,
  false_positive: <Tag color="red">ложное</Tag>,
}

function RecognitionTab({ run }: { run: StandRun }) {
  const [sceneId, setSceneId] = useState(run.scenes[0]?.id)
  const [view, setView] = useState<'frame.jpg' | 'truth.jpg' | 'detections.jpg' | 'crop.png'>('detections.jpg')
  const scene = useQuery({
    queryKey: ['stand-scene', run.run, sceneId],
    queryFn: () => api<StandScene>(`/api/stand/runs/${run.run}/scenes/${sceneId}`),
    enabled: !!sceneId,
  })
  const s = scene.data

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap>
        <Select
          style={{ minWidth: 380 }}
          value={sceneId}
          onChange={setSceneId}
          options={run.scenes.map((sc) => ({
            value: sc.id,
            label: `${sc.id.replace('scene_', 'Кадр ')} · ${LIGHTING[sc.lighting] ?? sc.lighting} · ${sc.rejected ? 'отбракован' : `${sc.detections} из ${sc.truth_count}`}${sc.has_person ? ' · человек' : ''}`,
          }))}
        />
        <Segmented
          value={view}
          onChange={(v) => setView(v as typeof view)}
          options={[
            { value: 'frame.jpg', label: 'Кадр камеры' },
            { value: 'truth.jpg', label: 'Разметка (истина)' },
            { value: 'detections.jpg', label: 'Распознавание' },
            { value: 'crop.png', label: 'Фрагмент 1:1' },
          ]}
        />
      </Space>
      {!s ? (
        <Spin />
      ) : (
        <>
          {s.rejected && <Alert type="warning" showIcon message={`Кадр отбракован до распознавания: ${s.rejected}`} />}
          <Row gutter={16}>
            <Col xs={24} xl={15}>
              <Card size="small" title={{
                'frame.jpg': 'Что видит камера (уменьшено в 4 раза, как подаётся в детектор)',
                'truth.jpg': 'Истинная разметка генератора: класс и ячейка',
                'detections.jpg': 'Распознавание: класс, уверенность, ячейка по модели камеры',
                'crop.png': 'Фрагмент кадра в полном разрешении 5472 × 3648',
              }[view]}>
                <AuthImage src={fileUrl(run.run, s.files[view])} alt={view} />
              </Card>
            </Col>
            <Col xs={24} xl={9}>
              <Card size="small" title="План стола: где объекты на самом деле и куда их поставила система">
                <AuthImage src={fileUrl(run.run, s.files['plan.png'])} alt="план" />
                <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 8 }}>
                  Зелёные — истина, красные — гомография пола, синие — модель камеры с учётом высоты поверхности.
                </Typography.Paragraph>
              </Card>
              <Card size="small" title="Кадр" style={{ marginTop: 16 }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="Свет">{LIGHTING[s.lighting] ?? s.lighting}</Descriptions.Item>
                  <Descriptions.Item label="Яркость / резкость">{s.quality.mean} / {s.quality.sharpness}</Descriptions.Item>
                  <Descriptions.Item label="Объектов в сцене">{s.truth_count}</Descriptions.Item>
                  <Descriptions.Item label="Распознано">{s.detections.length}</Descriptions.Item>
                  <Descriptions.Item label="Пропущено">{s.missed.length}</Descriptions.Item>
                  <Descriptions.Item label="Людей">{s.people.length}</Descriptions.Item>
                  <Descriptions.Item label="Помехи на столе">
                    {s.distractors.length ? s.distractors.map((d, i) => <Tag key={i}>{{ roll: 'скотч', pen: 'ручка', sheet: 'лист бумаги' }[d] ?? d}</Tag>) : 'нет'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Время обработки">
                    {s.timings_ms.total} мс (детекция {s.timings_ms.detect ?? '—'} мс)
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          </Row>
          <Card size="small" title="Распознанные объекты">
            <Table
              size="small"
              rowKey={(_, i) => String(i)}
              dataSource={s.detections}
              pagination={{ pageSize: 25, hideOnSinglePage: true }}
              columns={[
                { title: 'Класс', dataIndex: 'cls', render: (c: string) => CLASS_LABEL[c] ?? c },
                { title: 'Уверенность', dataIndex: 'confidence', render: (v: number) => v.toFixed(3), sorter: (a, b) => a.confidence - b.confidence },
                { title: 'Ячейка', dataIndex: 'cell', render: (v: string | null) => v ?? <Typography.Text type="secondary">вне ячеек</Typography.Text> },
                { title: 'Истинная', dataIndex: 'true_cell', render: (v: string | null | undefined) => v ?? '—' },
                { title: 'X; Y, м', key: 'xy', render: (_: unknown, r: StandDetectionRow) => `${r.x_m.toFixed(3)}; ${r.y_m.toFixed(3)}` },
                { title: 'Ошибка', dataIndex: 'error_cm', render: (v?: number) => (v !== undefined ? `${v.toFixed(2)} см` : '—'), sorter: (a, b) => (a.error_cm ?? 0) - (b.error_cm ?? 0) },
                {
                  title: 'По гомографии пола',
                  key: 'h',
                  render: (_: unknown, r: StandDetectionRow) => (
                    <Typography.Text type={r.true_cell !== undefined && r.cell_homography !== r.true_cell ? 'danger' : undefined}>
                      {r.cell_homography ?? 'вне ячеек'}
                      {r.error_homography_cm !== undefined && ` (${r.error_homography_cm.toFixed(1)} см)`}
                    </Typography.Text>
                  ),
                },
                { title: 'Итог', dataIndex: 'status', render: (v: StandDetectionRow['status']) => STATUS[v] },
              ]}
            />
            {s.missed.length > 0 && (
              <Alert
                style={{ marginTop: 8 }}
                type="warning"
                message={`Пропущены: ${s.missed.map((m) => `${CLASS_LABEL[m.cls] ?? m.cls} ${m.cell ?? 'вне ячеек'}`).join(', ')}`}
              />
            )}
          </Card>
        </>
      )}
    </Space>
  )
}

function DatasetTab({ run }: { run: StandRun }) {
  const ds = run.dataset
  if (!ds) return <Empty description="Датасет не найден. Запустите python -m cv.sim.dataset" />
  const total = Object.values(ds.class_counts).reduce((a, b) => a + b, 0)
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="Синтетический датасет: кадры рендерятся через модель камеры IMX183 + 12 мм над макетом, разметка YOLO создаётся автоматически."
        description="Каждый кадр — своя установка камеры (высота ±3 см, наклон ±1°, поворот ±2°, фокусное ±0,7 %), свой свет, шум и расфокус. Случайные расстановки коробок, контейнеров и паллет, помехи (бумага, ручки, скотч) и рука человека."
      />
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}><Card size="small"><Statistic title="Кадров обучения" value={ds.meta.train ?? 0} /></Card></Col>
        <Col xs={12} lg={6}><Card size="small"><Statistic title="Кадров валидации" value={ds.meta.val ?? 0} /></Card></Col>
        <Col xs={12} lg={6}><Card size="small"><Statistic title="Размеченных объектов (обучение)" value={total} /></Card></Col>
        <Col xs={12} lg={6}><Card size="small"><Statistic title="Размер кадра для детектора" value={ds.image_size.join(' × ')} /></Card></Col>
      </Row>
      <Card size="small" title="Объекты по классам">
        <Space wrap>
          {Object.entries(ds.class_counts).map(([c, n]) => (
            <Tag key={c} style={{ fontSize: 14, padding: '4px 10px' }}>
              {CLASS_LABEL[c] ?? c}: {n}
            </Tag>
          ))}
        </Space>
      </Card>
      <Card size="small" title="Образцы с разметкой (красный — коробка, синий — паллета, жёлтый — контейнер, фиолетовый — человек)">
        <Row gutter={[12, 12]}>
          {ds.samples.map((smp) => (
            <Col key={smp.file} xs={24} md={12} xl={6}>
              <AuthImage src={fileUrl(run.run, smp.file)} alt={smp.source} />
              <Typography.Text type="secondary">
                {smp.source} · объектов: {smp.objects}
              </Typography.Text>
            </Col>
          ))}
        </Row>
      </Card>
    </Space>
  )
}

export default function StandPage() {
  const runs = useQuery({ queryKey: ['stand-runs'], queryFn: () => api<StandRunListItem[]>('/api/stand/runs') })
  const [runId, setRunId] = useState<string | null>(null)
  const current = runId ?? runs.data?.[0]?.run ?? null
  const run = useQuery({
    queryKey: ['stand-run', current],
    queryFn: () => api<StandRun>(`/api/stand/runs/${current}`),
    enabled: current != null,
  })

  if (runs.isLoading) return <Spin />
  if (!runs.data?.length) {
    return <Empty description="Нет прогонов стенда. Запустите: uv run python -m cv.sim.demo" />
  }
  const r = run.data
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap align="center">
        <Typography.Title level={4} style={{ margin: 0 }}>
          Виртуальный стенд
        </Typography.Title>
        <Select
          style={{ minWidth: 260 }}
          value={current}
          onChange={setRunId}
          options={runs.data.map((x) => ({ value: x.run, label: `Прогон ${new Date(x.created).toLocaleString('ru-RU')}` }))}
        />
        {r && (
          <Typography.Text type="secondary">
            Модель {r.weights} · камера {r.camera.sensor.join('×')} на {r.camera.height_true_m.toFixed(2)} м · поле {r.camera.fov_floor_m.join(' × ')} м · {r.camera.mm_per_px_floor.toFixed(2)} мм/px
          </Typography.Text>
        )}
      </Space>
      {r ? (
        <>
          <Row gutter={[16, 16]}>
            <Col xs={12} lg={4}><Card size="small"><Statistic title="Кадров в прогоне" value={r.totals.scenes} /></Card></Col>
            <Col xs={12} lg={4}><Card size="small"><Statistic title="Распознано объектов" value={r.totals.detections} /></Card></Col>
            <Col xs={12} lg={4}><Card size="small"><Statistic title="Ложных / пропущено" value={`${r.totals.false_positives} / ${r.totals.missed}`} /></Card></Col>
            <Col xs={12} lg={4}><Card size="small"><Statistic title="Верная ячейка" value={r.totals.cell_accuracy * 100} precision={1} suffix="%" /></Card></Col>
            <Col xs={12} lg={4}><Card size="small"><Statistic title="Отбраковано кадров" value={r.totals.rejected} /></Card></Col>
            <Col xs={12} lg={4}><Card size="small"><Statistic title="Время на кадр" value={r.totals.mean_time_ms} suffix="мс" /></Card></Col>
          </Row>
          <Tabs
            defaultActiveKey="recognition"
            items={[
              { key: 'recognition', label: 'Как распознаёт', children: <RecognitionTab key={r.run} run={r} /> },
              { key: 'evaluation', label: 'Итоги испытания', children: <EvaluationTab run={r} /> },
              { key: 'dataset', label: 'Синтетические данные', children: <DatasetTab run={r} /> },
            ]}
          />
        </>
      ) : (
        <Spin />
      )}
    </Space>
  )
}
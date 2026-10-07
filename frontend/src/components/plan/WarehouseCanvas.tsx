import type Konva from 'konva'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Circle, Group, Layer, Line, Rect, Stage, Text } from 'react-konva'
import type { Cell, Point, Shelf, Twin, TwinObject } from '../../api/types'

export type Selection =
  | { kind: 'object'; object: TwinObject }
  | { kind: 'shelf'; shelf: Shelf }
  | { kind: 'cell'; cell: Cell; occupied: boolean }

const PAD = 24
const ZONE_FILL: Record<string, string> = {
  storage: '#cfe8ff',
  receiving: '#e0d4ff',
  shipping: '#ffd6e0',
  loading: '#ffe5b4',
  aisle: '#eeeeee',
}
const OBJECT_COLOR: Record<string, string> = {
  box: '#c08552',
  pallet: '#6d4c41',
  container: '#2f6db5',
}
const CELL_FREE = '#b7e4c7'
const CELL_OCCUPIED = '#f4978e'

interface Props {
  twin: Twin
  selected: Selection | null
  onSelect: (s: Selection | null) => void
  highlightObjectId?: number | null
}

/** Top-view footprint per (shelf, place): every level shares it, occupied if any level is. */
function footprints(twin: Twin) {
  const occupied = new Set(twin.occupied_cell_ids)
  const map = new Map<string, { cell: Cell; occupied: boolean }>()
  for (const cell of twin.cells) {
    const key = cell.shelf_id ? `s${cell.shelf_id}-${cell.place}` : `c${cell.id}`
    const prev = map.get(key)
    const isOcc = occupied.has(cell.id) || !!prev?.occupied
    if (!prev || (cell.level ?? 0) > (prev.cell.level ?? 0)) map.set(key, { cell, occupied: isOcc })
    else prev.occupied = isOcc
  }
  return [...map.values()]
}

export default function WarehouseCanvas({ twin, selected, onSelect, highlightObjectId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const [size, setSize] = useState({ width: 800, height: 500 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    )
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const { length_m: L, width_m: W } = twin.warehouse
  const k = Math.min((size.width - 2 * PAD) / L, (size.height - 2 * PAD) / W)
  const tx = (x: number) => PAD + x * k
  const ty = (y: number) => PAD + (W - y) * k
  const flat = (poly: Point[]) => poly.flatMap(([x, y]) => [tx(x), ty(y)])
  const fontSize = Math.max(10, Math.min(16, k * Math.min(L, W) * 0.03))

  const cells = useMemo(() => footprints(twin), [twin])

  useEffect(() => {
    stageRef.current?.scale({ x: 1, y: 1 })
    stageRef.current?.position({ x: 0, y: 0 })
  }, [twin.warehouse.id])

  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault()
    const stage = stageRef.current
    const pointer = stage?.getPointerPosition()
    if (!stage || !pointer) return
    const old = stage.scaleX()
    const next = Math.min(20, Math.max(0.5, old * (e.evt.deltaY > 0 ? 0.9 : 1.1)))
    const anchor = { x: (pointer.x - stage.x()) / old, y: (pointer.y - stage.y()) / old }
    stage.scale({ x: next, y: next })
    stage.position({ x: pointer.x - anchor.x * next, y: pointer.y - anchor.y * next })
  }

  const objRadius = Math.max(3, k * Math.min(L, W) * 0.012)

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#fafafa' }}>
      <Stage
        ref={stageRef}
        width={size.width}
        height={size.height}
        draggable
        onWheel={onWheel}
        onClick={(e) => e.target === e.target.getStage() && onSelect(null)}
      >
        <Layer>
          <Rect x={tx(0)} y={ty(W)} width={L * k} height={W * k} fill="#fff" stroke="#333" strokeWidth={2} />

          {twin.zones.map((z) => (
            <Line
              key={`z${z.id}`}
              points={flat(z.polygon)}
              closed
              fill={z.color ?? ZONE_FILL[z.type]}
              opacity={0.6}
              stroke="#999"
              strokeWidth={1}
              dash={[4, 4]}
              listening={false}
            />
          ))}

          {cells.map(({ cell, occupied }) => {
            const isSel = selected?.kind === 'cell' && selected.cell.id === cell.id
            return (
              <Line
                key={`c${cell.id}`}
                points={flat(cell.polygon)}
                closed
                fill={occupied ? CELL_OCCUPIED : CELL_FREE}
                stroke={isSel ? '#1677ff' : '#ffffff'}
                strokeWidth={isSel ? 2 : 0.5}
                onClick={() => onSelect({ kind: 'cell', cell, occupied })}
              />
            )
          })}

          {twin.shelves.map((s) => {
            const isSel = selected?.kind === 'shelf' && selected.shelf.id === s.id
            return (
              <Group
                key={`s${s.id}`}
                x={tx(s.x_m)}
                y={ty(s.y_m)}
                rotation={-s.rotation_deg}
                onClick={() => onSelect({ kind: 'shelf', shelf: s })}
              >
                <Rect
                  x={(-s.width_m * k) / 2}
                  y={(-s.depth_m * k) / 2}
                  width={s.width_m * k}
                  height={s.depth_m * k}
                  stroke={isSel ? '#1677ff' : '#37474f'}
                  strokeWidth={isSel ? 3 : 1.5}
                />
                <Text
                  x={(-s.width_m * k) / 2}
                  y={(-s.depth_m * k) / 2 - fontSize - 2}
                  width={s.width_m * k}
                  align="center"
                  text={s.code}
                  fontSize={fontSize}
                  fontStyle="bold"
                  fill="#37474f"
                />
              </Group>
            )
          })}

          {twin.zones.map((z) => {
            const minX = Math.min(...z.polygon.map((p) => p[0]))
            const maxY = Math.max(...z.polygon.map((p) => p[1]))
            return (
              <Text
                key={`zl${z.id}`}
                x={tx(minX) + 4}
                y={ty(maxY) + 4}
                text={z.name || z.code}
                fontSize={fontSize}
                fill="#444"
                listening={false}
              />
            )
          })}

          {twin.objects.map((o) => {
            if (o.x_m == null || o.y_m == null) return null
            const isSel =
              (selected?.kind === 'object' && selected.object.id === o.id) || highlightObjectId === o.id
            const missing = o.status === 'missing'
            return (
              <Circle
                key={`o${o.id}`}
                x={tx(o.x_m)}
                y={ty(o.y_m)}
                radius={isSel ? objRadius * 1.6 : objRadius}
                fill={missing ? 'transparent' : (OBJECT_COLOR[o.type_code] ?? '#555')}
                stroke={isSel ? '#1677ff' : missing ? '#999' : '#fff'}
                strokeWidth={isSel ? 3 : 1}
                dash={missing ? [3, 2] : undefined}
                onClick={() => onSelect({ kind: 'object', object: o })}
              />
            )
          })}
        </Layer>
      </Stage>
    </div>
  )
}

export type Role = 'admin' | 'operator' | 'viewer'
export type Point = [number, number]

export interface TokenOut {
  access_token: string
  token_type: string
  role: Role
}

export interface User {
  id: number
  login: string
  full_name: string
  role: Role
  is_active: boolean
}

export interface Warehouse {
  id: number
  name: string
  address: string
  length_m: number
  width_m: number
  height_m: number
}

export type ZoneType = 'storage' | 'receiving' | 'shipping' | 'loading' | 'aisle'

export interface Zone {
  id: number
  warehouse_id: number
  code: string
  name: string
  type: ZoneType
  polygon: Point[]
  color: string | null
}

export interface Shelf {
  id: number
  zone_id: number
  code: string
  x_m: number
  y_m: number
  rotation_deg: number
  width_m: number
  depth_m: number
  height_m: number
  levels: number
  places_per_level: number
}

export interface Cell {
  id: number
  shelf_id: number | null
  zone_id: number
  address: string
  level: number | null
  place: number | null
  polygon: Point[]
  capacity: number
}

export interface TwinObject {
  id: number
  type_code: string
  name: string
  status: 'active' | 'missing' | 'removed'
  cell_id: number | null
  zone_id: number | null
  x_m: number | null
  y_m: number | null
  last_seen_at: string
}

export interface Twin {
  warehouse: Warehouse
  zones: Zone[]
  shelves: Shelf[]
  cells: Cell[]
  objects: TwinObject[]
  occupied_cell_ids: number[]
}

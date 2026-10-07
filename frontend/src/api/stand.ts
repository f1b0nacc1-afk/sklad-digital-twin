export interface StandDetectionRow {
  cls: string
  confidence: number
  bbox: number[]
  x_m: number
  y_m: number
  cell: string | null
  zone: string | null
  cell_homography: string | null
  status: 'ok' | 'wrong_cell' | 'false_positive'
  true_cell?: string | null
  true_x_m?: number
  true_y_m?: number
  on_shelf?: boolean
  error_cm?: number
  error_homography_cm?: number
}

export interface StandScene {
  id: string
  lighting: string
  rejected: string | null
  quality: { ok: boolean; reason: string | null; mean: number; laplacian_var: number; sharpness: number }
  timings_ms: Record<string, number>
  truth_count: number
  has_person: boolean
  people: { confidence: number }[]
  detections: StandDetectionRow[]
  missed: { cls: string; cell: string | null }[]
  distractors: string[]
  files: Record<'frame.jpg' | 'crop.png' | 'truth.jpg' | 'detections.jpg' | 'plan.png', string>
}

interface ClassCounts {
  precision: number
  recall: number
  tp: number
  fp: number
  fn: number
}

interface Localization {
  cell_accuracy: number
  rmse_cm: number
  p95_cm: number
  shelf_rmse_cm: number
}

interface CalibErrors {
  homography_cm: number
  camera_model_cm: number
}

export interface StandEvaluation {
  weights: string
  scenes: number
  camera: { height_true_m: number; height_estimated_m: number; fov_floor_m: number[]; mm_per_px_floor: number }
  calibration: {
    marker_fit_rmse_cm: number
    floor_control_points: CalibErrors
    shelf_top_points: CalibErrors
  }
  detection: Record<string, ClassCounts>
  count_mae: number | null
  mean_confidence_tp: number | null
  localization: Record<'floor_homography' | 'camera_model', Localization>
  people: { with_person: number; rejected: number; accepted_partial: number }
  timing_ms: { mean: number; max: number }
  quality_checks: Record<string, { ok: boolean; reason: string | null; sharpness?: number; mean: number }>
  map: { map50: number; per_class_map50: Record<string, number> } | null
}

export interface StandRun {
  run: string
  created: string
  weights: string
  stand: { name: string; size_m: number[]; cells: number; zones: { code: string; name: string }[] }
  camera: {
    sensor: number[]
    height_true_m: number
    height_estimated_m: number
    fov_floor_m: number[]
    mm_per_px_floor: number
    work_scale: number
  }
  calibration: StandEvaluation['calibration']
  totals: {
    scenes: number
    rejected: number
    detections: number
    false_positives: number
    missed: number
    cell_accuracy: number
    cell_accuracy_homography: number
    mean_time_ms: number
  }
  evaluation: StandEvaluation | null
  dataset: {
    meta: { train?: number; val?: number; objects?: number; seed?: number }
    class_counts: Record<string, number>
    samples: { file: string; source: string; objects: number }[]
    image_size: number[]
  } | null
  scenes: { id: string; lighting: string; rejected: string | null; detections: number; truth_count: number; has_person: boolean }[]
}

export interface StandRunListItem {
  run: string
  created: string
  weights: string
  totals: StandRun['totals']
}

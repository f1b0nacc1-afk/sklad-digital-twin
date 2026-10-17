# Interview guide — Warehouse Digital Twin

**Ivan Iliukhin** — Applied AI / CV / Python  
Scope: solo R&D prototype (academic / portfolio). Metrics cited here are from the **virtual (synthetic) stand** in [05_Виртуальный_стенд.md](05_Виртуальный_стенд.md), unless noted. No production warehouse deployment is claimed.

---

### 1. Why did floor homography fail (~83%), and what did you do instead?

**Q:** Why isn’t a single image→floor homography enough for cell assignment?

**A:** Homography maps every pixel as if it lies on the floor plane. Tall objects (shelf tops) project with **height parallax**: the top face is shifted outward from the optical axis. On the maquette, the upper shelf is ~13 cm high with the camera at ~1.15 m; a point 40 cm off-axis shifts by roughly \(0.4 \times 0.13 / (1.15 - 0.13) \approx 5\) cm while cells are only ~11×12 cm. On the virtual-stand test (40 frames), floor homography reached **82.7%** correct cells (RMSE 3.7 cm) vs the ≥90% target — so it failed the written ТЗ rule.

**Fix:** keep full camera calibration (**K + pose** from the same ≥4 markers via `solvePnP`) and intersect the viewing ray with the **support surface** the object stands on (floor or shelf top + nominal class height). Implemented as `SurfaceAwareMapper` in `cv/pipeline.py`. Same test session: **100%** cell accuracy, RMSE **0.55 cm**.

---

### 2. Why is synthetic mAP an upper bound?

**Q:** You report mAP@0.5 = 0.995. Is that production-ready?

**A:** No. The detector (YOLO11s, 500 train / 100 val synthetic frames) only ever saw **rendered** boxes/pallets/containers. Textures, glare, crumple, and real sensor noise are missing. On the held-out synthetic test the number looks strong (0.995 mAP@0.5; box P/R 1.00/1.00), but that is an **upper bound** useful for pipeline debugging and pretraining. Real accuracy requires a camera-captured labeled set and fine-tuning — explicitly called out in the virtual-stand conclusions.

---

### 3. Walk through the pipeline stages and failure modes

**Q:** What happens to one frame end-to-end?

**A:**

| Stage | Role | Typical failure |
|---|---|---|
| Capture | File / video / Basler (Hikrobot stub) | No camera, bad exposure |
| Quality (`cv/quality.py`) | Brightness, overexposure, sharpness | Absolute Laplacian variance rejected sharp **dark** frames; fixed with **normalized** sharpness `var(Laplacian)/var(image)×1000` |
| Detect | Mono→3ch, scale (~4× down), tiling, YOLO, NMS | Misses / false positives on clutter; paper sheets should stay non-box |
| Person gate | Reject if person boxes cover >20% of frame | Hand covering cells → later matching must not mark objects under `person` as disappeared |
| Map | Homography or surface-aware camera model | Wrong plane → wrong cell |
| Locate | Point-in-polygon zone/cell | Calibration drift, FOV clipping at table edge |

Timings on the virtual stand (GPU): ~**130 ms** average / **266 ms** max for quality + detect + locate (target ≤ 3 s).

---

### 4. Why FastAPI + PostgreSQL + Redis?

**Q:** Why this backend stack?

**A:**

- **FastAPI** — typed REST + OpenAPI for warehouse CRUD, twin snapshot, auth; fits async I/O around scan uploads and CV job status.
- **PostgreSQL** — relational model from the ТЗ (warehouses → zones → racks → cells, scans, detections, events, calibrations); Alembic migrations keep schema reviewable.
- **Redis** — job queue for the worker service (long CV work off the request thread); Compose already wires `api` + `worker` to Redis. Scan matching / occupancy workers are the next iteration on that queue.

Roles use JWT + bcrypt (admin / operator / viewer). This is an information system that **observes** the warehouse; it does not drive PLCs or WMS actuators.

---

### 5. What would you validate on real hardware first?

**Q:** Virtual stand passed — what do you still need from Basler/Hikrobot + maquette?

**A:**

1. First live grab (`scripts/grab_one.py`) and retune quality thresholds (normalized sharpness, exposure).
2. Marker click accuracy and pose solve on a real calibration target (simulation uses σ ≈ 1.5 px click noise).
3. FOV / height: docs recommend **~1.2 m** camera height for the 1.2×0.8 m table (1.0 m is tight; 1° tilt can clip the edge).
4. Collect **300–500** labeled real frames; measure mAP and cell accuracy again with `SurfaceAwareMapper`.
5. Confirm person-in-frame policy and that lower rack levels stay “unknown” for occupancy (not visible top-down).

Until those steps, do not claim hardware-validated metrics.

---

### 6. YOLO vs classical CV — when would you switch?

**Q:** Why YOLO here? Would classical CV suffice?

**A:** Top-down industrial views are relatively constrained (mono, known classes, limited poses), so classical pipelines (edges, contours, template matching, color — weak on mono) can work for **high-contrast boxes on empty floors**. YOLO wins when classes multiply (box / pallet / container / person), clutter appears (tape rolls, paper sheets), and lighting modes vary — which the stand already injects.

Tradeoff: YOLO needs labeled data and a GPU for comfortable latency; classical methods are cheaper to run and easier to explain, but brittle under defocus, shadows, and distractors. Practical path in this repo: **synthetic YOLO for pipeline bring-up**, then **fine-tune on real frames**; keep classical tools for markers / sharpness / barcodes (`zxing-cpp` optional), not as the primary object detector.

---

### 7. How does the surface-aware mapper choose the plane?

**Q:** Multiple shelf heights — how do you pick Z?

**A:** Surfaces are sorted **highest first**. For a detection, the ray is intersected with `surface.z + nominal_class_height`; if the (x, y) lands inside that surface polygon (small buffer), that hit wins. From above, a higher object occludes whatever is below — matching the visibility model in the ТЗ (lower levels not observed). Fallback: project to floor-level + class height.

---

### 8. What is still unfinished in the product sense?

**Q:** What should a reviewer not expect to work yet?

**A:** Cross-scan **matching** (appeared / moved / disappeared), occupancy snapshots with “unknown” cells, full `POST /api/scans` worker path, chessboard calibration API, Hikrobot live path, barcode-in-bbox, and most admin/scan UI screens. The digital-twin **plan UI**, warehouse CRUD, geo services, CV pipeline, and virtual-stand demo page are in place. Roadmap: [04_Дорожная_карта_разработки.md](04_Дорожная_карта_разработки.md).

---

### 9. Scaling from maquette (A) to a room demo (B)?

**Q:** Does the geometry problem get easier or harder at room scale?

**A:** Harder for homography. Docs note a warehouse-like case: shelf top 2 m, camera 5 m → shift ≈ \(2/(5-2) \approx 67\%\) of the radial distance to the axis. Surface-aware mapping becomes **more** important, not less. Coverage is still limited to one camera FOV; a full 30×15 m warehouse is a data model, not a claim of multi-camera production coverage.

---

### 10. How do you talk about this project ethically in interviews?

**Q:** Is this commercial / employer IP?

**A:** Framed as **solo R&D / academic prototype** (ТЗ: graduation-style work). Do not brand it as Germet-Pro or claim client production. Quote only virtual-stand numbers with the synthetic caveat; say hardware validation is planned, not done.

---

### 11. Performance — do you need tiling / binning?

**Q:** 20 MP frames — how do you meet the ≤3 s GPU budget?

**A:** Working resolution is scaled (~¼ → ~1368×912; a 4 cm box ≈ 43 px). Virtual-stand end-to-end was ~130 ms average on GPU — roughly **20×** headroom vs 3 s, so full-resolution binning is not required for the current detector path. Tiling remains available for small objects if real data demands it (SAHI optional extra).

---

### 12. Quality gate: why normalize Laplacian variance?

**Q:** What bug did the stand expose in frame QC?

**A:** Absolute `var(Laplacian)` scales with contrast², so a sharp but dim frame scored ~57 vs threshold 100 and was rejected (10/40 dark frames). Normalized metric separates true defocus (σ ≥ 3 px → score ≤ 7.6) from dim-but-sharp frames (scores 46–174 across lighting). Threshold 20 on the stand; must be re-checked on real grabs.

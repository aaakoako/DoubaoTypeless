import Konva from "konva";

export type Tool =
  | "pen"
  | "marker"
  | "highlight"
  | "arrow"
  | "rect"
  | "ellipse"
  | "line"
  | "number"
  | "crop"
  | "text"
  | "eraser"
  | "mask"
  | "select"
  | "pan";

type Crop = { x: number; y: number; w: number; h: number };
type Snapshot = { json: string; crop: Crop; numbers: number };

export class SharedEditor {
  stage: Konva.Stage;
  layer: Konva.Layer;
  imageLayer: Konva.Layer;
  tool: Tool = "pen";
  color = "#D45243";
  width = 5;
  ops = 0;
  crop: Crop;
  private drawing: Konva.Shape | null = null;
  private numbers = 0;
  private start = { x: 0, y: 0 };
  private undoStack: Snapshot[] = [];
  private redoStack: Snapshot[] = [];
  private pointers = new Map<number, { x: number; y: number }>();
  private pinch: { dist: number; scale: number; x: number; y: number } | null = null;
  private bg: Konva.Image | null = null;
  private source = { w: 1600, h: 1000 };

  constructor(container: HTMLDivElement, width = 1600, height = 1000) {
    this.source = { w: width, h: height };
    this.crop = { x: 0, y: 0, w: width, h: height };
    this.stage = new Konva.Stage({
      container,
      width: container.clientWidth || 390,
      height: container.clientHeight || 420,
    });
    this.imageLayer = new Konva.Layer();
    this.layer = new Konva.Layer();
    this.stage.add(this.imageLayer);
    this.stage.add(this.layer);
    const el = this.stage.container();
    el.style.touchAction = "none";
    el.addEventListener("pointerdown", (e) => this.onPointerDown(e));
    el.addEventListener("pointermove", (e) => this.onPointerMove(e));
    el.addEventListener("pointerup", (e) => this.onPointerUp(e));
    el.addEventListener("pointercancel", (e) => this.onPointerUp(e, true));
  }

  resize(): void {
    const node = this.stage.container();
    this.stage.size({ width: node.clientWidth, height: node.clientHeight || 420 });
    this.fit();
  }

  loadImage(src: string, w: number, h: number): void {
    this.source = { w, h };
    this.crop = { x: 0, y: 0, w, h };
    const image = new window.Image();
    image.onload = () => {
      this.bg = new Konva.Image({ image, x: 0, y: 0, width: w, height: h });
      this.imageLayer.destroyChildren();
      this.imageLayer.add(this.bg);
      this.fit();
    };
    image.src = src;
  }

  addBlankBoard(w = 1600, h = 1000): void {
    this.source = { w, h };
    this.crop = { x: 0, y: 0, w, h };
        const rect = new Konva.Rect({ x: 0, y: 0, width: w, height: h, fill: "#f7f6f1" });
        this.imageLayer.destroyChildren();
        this.imageLayer.add(rect);
        for (let x = 40; x < w; x += 40) {
          for (let y = 40; y < h; y += 40) {
            this.imageLayer.add(new Konva.Circle({ x, y, radius: 1.2, fill: "#d5ddd6", listening: false, name: "grid" }));
          }
        }
    this.fit();
  }

  private fit(): void {
    const scale = Math.min(this.stage.width() / this.source.w, this.stage.height() / this.source.h, 1);
    this.stage.scale({ x: scale, y: scale });
    this.stage.position({
      x: (this.stage.width() - this.source.w * scale) / 2,
      y: (this.stage.height() - this.source.h * scale) / 2,
    });
    this.stage.batchDraw();
  }

  private world(ev: PointerEvent) {
    const rect = this.stage.container().getBoundingClientRect();
    const transform = this.stage.getAbsoluteTransform().copy().invert();
    return transform.point({ x: ev.clientX - rect.left, y: ev.clientY - rect.top });
  }

  private snapshot(): Snapshot {
    return { json: this.layer.toJSON(), crop: { ...this.crop }, numbers: this.numbers };
  }

  private pushUndo(): void {
    this.undoStack.push(this.snapshot());
    if (this.undoStack.length > 50) this.undoStack.shift();
    this.redoStack = [];
  }

  undo(): void {
    const prev = this.undoStack.pop();
    if (!prev) return;
    this.redoStack.push(this.snapshot());
    this.restore(prev);
  }

  redo(): void {
    const next = this.redoStack.pop();
    if (!next) return;
    this.undoStack.push(this.snapshot());
    this.restore(next);
  }

  private restore(snap: Snapshot): void {
    this.layer.destroy();
    this.layer = Konva.Node.create(snap.json, this.stage.container());
    this.stage.add(this.layer);
    this.crop = snap.crop;
    this.numbers = snap.numbers;
    this.ops = this.layer.getChildren().length;
    this.stage.batchDraw();
  }

  private strokeForTool(): { color: string; width: number; opacity: number } {
    if (this.tool === "highlight") return { color: this.color, width: this.width * 3, opacity: 0.25 };
    if (this.tool === "marker") return { color: this.color, width: this.width * 2, opacity: 1 };
    return { color: this.color, width: this.width, opacity: 1 };
  }

  private onPointerDown(ev: PointerEvent): void {
    ev.preventDefault();
    (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
    this.pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (this.pointers.size === 2) {
      const pts = [...this.pointers.values()];
      this.pinch = {
        dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y),
        scale: this.stage.scaleX(),
        x: this.stage.x(),
        y: this.stage.y(),
      };
      if (this.drawing) {
        this.drawing.destroy();
        this.drawing = null;
      }
      return;
    }
    const p = this.world(ev);
    this.start = p;
    if (this.tool === "number") {
      this.pushUndo();
      this.numbers += 1;
      const g = new Konva.Group({ x: p.x, y: p.y, name: "number" });
      g.add(new Konva.Circle({ radius: 18, fill: this.color }));
      g.add(new Konva.Text({ text: String(this.numbers), fill: "#fff", fontSize: 16, offsetX: 5, offsetY: 8 }));
      this.layer.add(g);
      this.ops += 1;
      this.layer.draw();
      return;
    }
    if (this.tool === "text") {
      const value = window.prompt("添加文字", "") || "";
      if (!value) return;
      this.pushUndo();
      this.layer.add(new Konva.Text({ x: p.x, y: p.y, text: value, fill: this.color, fontSize: 28 }));
      this.ops += 1;
      this.layer.draw();
      return;
    }
    if (this.tool === "eraser") {
      const hit = this.layer.getIntersection(p);
      if (hit) {
        this.pushUndo();
        const parent = hit.getParent();
        (parent instanceof Konva.Group ? parent : hit).destroy();
        this.ops = Math.max(0, this.ops - 1);
        this.layer.draw();
      }
      return;
    }
    const stroke = this.strokeForTool();
    if (this.tool === "pen" || this.tool === "marker" || this.tool === "highlight") {
      this.drawing = new Konva.Line({
        stroke: stroke.color,
        strokeWidth: stroke.width,
        opacity: stroke.opacity,
        lineCap: "round",
        lineJoin: "round",
        points: [p.x, p.y, p.x, p.y],
      });
    } else if (this.tool === "rect" || this.tool === "crop" || this.tool === "mask") {
      this.drawing = new Konva.Rect({
        x: p.x,
        y: p.y,
        width: 1,
        height: 1,
        stroke: this.tool === "crop" ? "#167D71" : this.color,
        fill: this.tool === "mask" ? "#111111" : undefined,
        strokeWidth: this.width,
        dash: this.tool === "crop" ? [8, 6] : undefined,
      });
    } else if (this.tool === "ellipse") {
      this.drawing = new Konva.Ellipse({ x: p.x, y: p.y, radiusX: 1, radiusY: 1, stroke: this.color, strokeWidth: this.width });
    } else if (this.tool === "arrow") {
      this.drawing = new Konva.Arrow({
        points: [p.x, p.y, p.x + 1, p.y + 1],
        stroke: this.color,
        fill: this.color,
        strokeWidth: this.width,
      });
    } else if (this.tool === "line") {
      this.drawing = new Konva.Line({ points: [p.x, p.y, p.x + 1, p.y + 1], stroke: this.color, strokeWidth: this.width });
    }
    if (this.drawing) this.layer.add(this.drawing);
  }

  private onPointerMove(ev: PointerEvent): void {
    if (!this.pointers.has(ev.pointerId)) return;
    ev.preventDefault();
    this.pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (this.pointers.size >= 2 && this.pinch) {
      const pts = [...this.pointers.values()];
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const scale = Math.max(0.25, Math.min(4, this.pinch.scale * (dist / Math.max(this.pinch.dist, 1))));
      this.stage.scale({ x: scale, y: scale });
      this.stage.batchDraw();
      return;
    }
    if (!this.drawing) return;
    const p = this.world(ev);
    if (this.drawing instanceof Konva.Line && !(this.drawing instanceof Konva.Arrow)) {
      if (this.tool === "line") this.drawing.points([this.start.x, this.start.y, p.x, p.y]);
      else this.drawing.points(this.drawing.points().concat([p.x, p.y]));
    } else if (this.drawing instanceof Konva.Rect) {
      this.drawing.width(p.x - this.start.x);
      this.drawing.height(p.y - this.start.y);
    } else if (this.drawing instanceof Konva.Ellipse) {
      this.drawing.radiusX(Math.abs(p.x - this.start.x));
      this.drawing.radiusY(Math.abs(p.y - this.start.y));
    } else if (this.drawing instanceof Konva.Arrow) {
      this.drawing.points([this.start.x, this.start.y, p.x, p.y]);
    }
    this.layer.batchDraw();
  }

  private onPointerUp(ev: PointerEvent, cancel = false): void {
    this.pointers.delete(ev.pointerId);
    if (this.pinch) {
      if (!this.pointers.size) this.pinch = null;
      this.drawing = null;
      return;
    }
    if (this.drawing && !cancel) {
      if (this.tool === "crop" && this.drawing instanceof Konva.Rect) {
        const w = Math.abs(this.drawing.width());
        const h = Math.abs(this.drawing.height());
        if (w >= 64 && h >= 64) {
          this.pushUndo();
          this.crop = {
            x: Math.min(this.drawing.x(), this.drawing.x() + this.drawing.width()),
            y: Math.min(this.drawing.y(), this.drawing.y() + this.drawing.height()),
            w,
            h,
          };
        }
        this.drawing.destroy();
      } else {
        this.pushUndo();
        this.ops += 1;
      }
    } else if (this.drawing && cancel) {
      this.drawing.destroy();
    }
    this.drawing = null;
  }

  addWireframe(): void {
    this.pushUndo();
    this.layer.add(
      new Konva.Rect({ x: this.source.w * 0.2, y: this.source.h * 0.3, width: this.source.w * 0.6, height: this.source.h * 0.14, stroke: "#167D71", strokeWidth: 5, cornerRadius: 8 })
    );
    this.layer.add(new Konva.Text({ x: this.source.w * 0.38, y: this.source.h * 0.34, text: "确认按钮", fill: "#167D71", fontSize: 32 }));
    this.ops += 1;
    this.layer.draw();
  }

  exportBlob(): Promise<Blob> {
    const url = this.stage.toDataURL({
      x: this.crop.x * this.stage.scaleX() + this.stage.x(),
      y: this.crop.y * this.stage.scaleY() + this.stage.y(),
      width: this.crop.w * this.stage.scaleX(),
      height: this.crop.h * this.stage.scaleY(),
      pixelRatio: 2,
      mimeType: "image/png",
    });
    return fetch(url).then((r) => r.blob());
  }
}

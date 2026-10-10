import { useEffect, useRef, useState } from 'react';
import { Cpu, Zap, Database, Mic, Sparkles, RotateCcw, Layers, ShieldCheck } from 'lucide-react';
import { useVoiceStore } from '../../store/voiceStore';
import { useChatStore, MODEL_CATALOG, type AuraModelId } from '../../store/chatStore';
import { useWakeWord } from '../../hooks/useWakeWord';

interface Point3D {
  x: number;
  y: number;
  z: number;
  baseX: number;
  baseY: number;
  baseZ: number;
  pulseOffset: number;
}

interface RingParticle3D {
  angle: number;
  speed: number;
  radius: number;
  tiltX: number;
  tiltZ: number;
  color: string;
  size: number;
}

interface NeuralCore3DProps {
  expanded?: boolean;
}

export const NeuralCore3D = ({ expanded = false }: NeuralCore3DProps) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const {
    voiceState,
    wakeWordStatus,
    wakeWordEnabled,
    isMicActive,
    vramUsageMB,
    vramTotalMB
  } = useVoiceStore();

  const {
    isStreaming,
    selectedModel,
    setSelectedModel,
    liveTps,
    peakTps,
    contextWindowLabel
  } = useChatStore();

  const { triggerManualVoice } = useWakeWord();

  // Interactive 3D rotation state
  const rotRef = useRef({ x: 0.35, y: 0.6, z: 0.1, velX: 0, velY: 0 });
  const isDraggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(1.0);
  const [interactiveHint, setInteractiveHint] = useState('Drag to orbit 3D core • Scroll to zoom');

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let time = 0;

    // 1. Build Fibonacci 3D Geodesic Sphere Vertices
    const numPoints = expanded ? 190 : 135;
    const points: Point3D[] = [];
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    for (let i = 0; i < numPoints; i++) {
      const y = 1 - (i / (numPoints - 1)) * 2;
      const radiusAtY = Math.sqrt(1 - y * y);
      const theta = goldenAngle * i;
      const x = Math.cos(theta) * radiusAtY;
      const z = Math.sin(theta) * radiusAtY;
      points.push({
        x,
        y,
        z,
        baseX: x,
        baseY: y,
        baseZ: z,
        pulseOffset: Math.random() * Math.PI * 2
      });
    }

    // 2. Build Inner 3D Octahedron/Icosahedron Core Vertices
    const innerCore: [number, number, number][] = [
      [0, 0.55, 0],
      [0, -0.55, 0],
      [0.55, 0, 0],
      [-0.55, 0, 0],
      [0, 0, 0.55],
      [0, 0, -0.55]
    ];

    const innerEdges: [number, number][] = [
      [0, 2], [0, 3], [0, 4], [0, 5],
      [1, 2], [1, 3], [1, 4], [1, 5],
      [2, 4], [4, 3], [3, 5], [5, 2]
    ];

    // 3. Build 3D Gyroscope Orbital Rings
    const ringParticles: RingParticle3D[] = [];
    const ringConfigs = [
      { radius: 1.32, tiltX: 0.55, tiltZ: 0.25, color: '#00F0FF', count: 36, speed: 0.012 },
      { radius: 1.52, tiltX: -0.45, tiltZ: 0.65, color: '#A855F7', count: 32, speed: -0.009 },
      { radius: 1.72, tiltX: 1.05, tiltZ: -0.35, color: '#10B981', count: 28, speed: 0.007 }
    ];

    ringConfigs.forEach((rc) => {
      for (let i = 0; i < rc.count; i++) {
        ringParticles.push({
          angle: (i / rc.count) * Math.PI * 2,
          speed: rc.speed,
          radius: rc.radius,
          tiltX: rc.tiltX,
          tiltZ: rc.tiltZ,
          color: rc.color,
          size: i % 4 === 0 ? 2.6 : 1.3
        });
      }
    });

    // Resize observer for sharp Retina rendering
    const updateSize = () => {
      if (!canvas) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, rect.width * dpr);
      canvas.height = Math.max(1, rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    updateSize();
    window.addEventListener('resize', updateSize);

    // 3D Rotation Helper
    const rotate3D = (x: number, y: number, z: number, rx: number, ry: number, rz: number) => {
      // Rotate X
      const cosX = Math.cos(rx);
      const sinX = Math.sin(rx);
      const y1 = y * cosX - z * sinX;
      const z1 = y * sinX + z * cosX;

      // Rotate Y
      const cosY = Math.cos(ry);
      const sinY = Math.sin(ry);
      const x2 = x * cosY + z1 * sinY;
      const z2 = -x * sinY + z1 * cosY;

      // Rotate Z
      const cosZ = Math.cos(rz);
      const sinZ = Math.sin(rz);
      const x3 = x2 * cosZ - y1 * sinZ;
      const y3 = x2 * sinZ + y1 * cosZ;

      return { x: x3, y: y3, z: z2 };
    };

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      const cx = width / 2;
      const cy = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Determine active energy state
      const isSpeaking = voiceState === 'speaking';
      const isListening =
        voiceState === 'listening' ||
        wakeWordStatus === 'capturing' ||
        wakeWordStatus === 'detected' ||
        isMicActive;

      const energyMultiplier = isStreaming
        ? 2.6
        : isSpeaking
        ? 2.2
        : isListening
        ? 1.9
        : 1.0;

      time += 0.018 * energyMultiplier;

      // Auto-rotate + inertia damping
      if (!isDraggingRef.current) {
        rotRef.current.y += 0.0065 * energyMultiplier + rotRef.current.velY;
        rotRef.current.x += 0.0022 * energyMultiplier + rotRef.current.velX;
        rotRef.current.velX *= 0.92;
        rotRef.current.velY *= 0.92;
      }

      const baseScale = Math.min(width, height) * (expanded ? 0.25 : 0.26) * zoomRef.current;
      const fov = 3.8;

      // Primary theme color based on state
      const primaryRgb = isSpeaking
        ? '168, 85, 247' // Purple vocal harmonic
        : isListening
        ? '16, 185, 129' // Emerald active radar
        : isStreaming
        ? '0, 240, 255' // Cyan hyper-stream
        : selectedModel === 'nvidia/nemotron-3-ultra'
        ? '16, 185, 129' // NVIDIA Emerald-Cyan
        : '0, 240, 255';

      // Ambient 3D Core Volumetric Glow
      const coreGlow = ctx.createRadialGradient(cx, cy, 4, cx, cy, baseScale * 1.65);
      coreGlow.addColorStop(0, `rgba(${primaryRgb}, 0.32)`);
      coreGlow.addColorStop(0.45, `rgba(168, 85, 247, 0.10)`);
      coreGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = coreGlow;
      ctx.beginPath();
      ctx.arc(cx, cy, baseScale * 1.65, 0, Math.PI * 2);
      ctx.fill();

      // Project Inner 3D Polyhedron Core
      const projectedInner = innerCore.map(([ix, iy, iz]) => {
        const pulse = 1 + 0.14 * Math.sin(time * 2.5);
        const r = rotate3D(
          ix * pulse,
          iy * pulse,
          iz * pulse,
          -rotRef.current.x * 1.4,
          -rotRef.current.y * 1.6,
          time * 0.5
        );
        const persp = fov / (fov + r.z);
        return {
          sx: cx + r.x * baseScale * persp,
          sy: cy + r.y * baseScale * persp,
          z: r.z
        };
      });

      // Draw Inner 3D Polyhedron Wireframe
      ctx.lineWidth = 1.25;
      innerEdges.forEach(([i, j]) => {
        const p1 = projectedInner[i];
        const p2 = projectedInner[j];
        ctx.strokeStyle = `rgba(${primaryRgb}, 0.55)`;
        ctx.beginPath();
        ctx.moveTo(p1.sx, p1.sy);
        ctx.lineTo(p2.sx, p2.sy);
        ctx.stroke();
      });

      // Project Fibonacci Geodesic Sphere Points with 3D Harmonic Deformation
      const projectedPoints: {
        sx: number;
        sy: number;
        z: number;
        persp: number;
        energy: number;
      }[] = [];

      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        // Harmonic 3D displacement when speaking, listening, or streaming
        const waveAmp = isSpeaking
          ? 0.16 * Math.sin(time * 4.0 + p.baseY * 6.0 + p.pulseOffset)
          : isListening
          ? 0.12 * Math.cos(time * 3.5 + p.baseX * 5.0)
          : isStreaming
          ? 0.10 * Math.sin(time * 5.0 + i * 0.3)
          : 0.03 * Math.sin(time * 1.5 + p.pulseOffset);

        const deform = 1 + waveAmp;
        const r = rotate3D(
          p.baseX * deform,
          p.baseY * deform,
          p.baseZ * deform,
          rotRef.current.x,
          rotRef.current.y,
          rotRef.current.z
        );

        const persp = fov / (fov + r.z);
        projectedPoints.push({
          sx: cx + r.x * baseScale * persp,
          sy: cy + r.y * baseScale * persp,
          z: r.z,
          persp,
          energy: Math.abs(waveAmp)
        });
      }

      // Draw 3D Synaptic Connections between nearby Geodesic Nodes
      const maxDistSq = (baseScale * 0.42) ** 2;
      ctx.lineWidth = 0.75;

      for (let i = 0; i < projectedPoints.length; i++) {
        const p1 = projectedPoints[i];
        if (p1.z > 0.65) continue; // Cull far back connections for clean depth

        for (let j = i + 1; j < projectedPoints.length; j++) {
          const p2 = projectedPoints[j];
          const dx = p1.sx - p2.sx;
          const dy = p1.sy - p2.sy;
          const distSq = dx * dx + dy * dy;

          if (distSq < maxDistSq) {
            const depthAlpha = Math.max(0.05, (1 - (p1.z + p2.z) * 0.35) * (1 - distSq / maxDistSq));
            ctx.strokeStyle = `rgba(${primaryRgb}, ${depthAlpha * 0.42})`;
            ctx.beginPath();
            ctx.moveTo(p1.sx, p1.sy);
            ctx.lineTo(p2.sx, p2.sy);
            ctx.stroke();
          }
        }
      }

      // Draw 3D Geodesic Nodes sorted by Z-depth
      projectedPoints.forEach((pt) => {
        const depthFactor = Math.max(0.18, (1.4 - pt.z) * 0.65);
        const radius = Math.max(1.1, (expanded ? 2.4 : 2.0) * pt.persp * (1 + pt.energy * 1.8));

        ctx.fillStyle =
          pt.z < -0.2
            ? `rgba(255, 255, 255, ${Math.min(1, depthFactor)})`
            : `rgba(${primaryRgb}, ${Math.min(0.95, depthFactor)})`;

        ctx.beginPath();
        ctx.arc(pt.sx, pt.sy, radius, 0, Math.PI * 2);
        ctx.fill();
      });

      // Draw 3D Gyroscope Orbital Rings
      ringParticles.forEach((rp) => {
        rp.angle += rp.speed * energyMultiplier;
        const rx = Math.cos(rp.angle) * rp.radius;
        const rz = Math.sin(rp.angle) * rp.radius;
        // Apply ring's intrinsic 3D tilt + global camera rotation
        const tilted = rotate3D(rx, 0, rz, rp.tiltX, 0, rp.tiltZ);
        const final3D = rotate3D(
          tilted.x,
          tilted.y,
          tilted.z,
          rotRef.current.x * 0.6,
          rotRef.current.y * 0.6,
          0
        );

        const persp = fov / (fov + final3D.z);
        const sx = cx + final3D.x * baseScale * persp;
        const sy = cy + final3D.y * baseScale * persp;
        const alpha = Math.max(0.15, (1.5 - final3D.z) * 0.55);

        ctx.fillStyle = rp.color;
        ctx.globalAlpha = Math.min(0.95, alpha);
        ctx.beginPath();
        ctx.arc(sx, sy, rp.size * persp, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1.0;

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', updateSize);
    };
  }, [voiceState, wakeWordStatus, isMicActive, isStreaming, selectedModel, expanded]);

  // Mouse handlers for interactive 3D orbit rotation
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = true;
    lastMouseRef.current = { x: e.clientX, y: e.clientY };
    setInteractiveHint('3D Orbit Active — Release to float');
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastMouseRef.current.x;
    const dy = e.clientY - lastMouseRef.current.y;
    lastMouseRef.current = { x: e.clientX, y: e.clientY };

    rotRef.current.y += dx * 0.008;
    rotRef.current.x += dy * 0.008;
    rotRef.current.velY = dx * 0.0015;
    rotRef.current.velX = dy * 0.0015;
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
    setInteractiveHint('Drag to orbit 3D core • Scroll to zoom');
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const next = zoomRef.current - e.deltaY * 0.0008;
    zoomRef.current = Math.min(1.45, Math.max(0.65, next));
  };

  const handleResetView = () => {
    rotRef.current = { x: 0.35, y: 0.6, z: 0.1, velX: 0, velY: 0 };
    zoomRef.current = 1.0;
  };

  const vramGB = (vramUsageMB / 1024).toFixed(1);
  const totalGB = (vramTotalMB / 1024).toFixed(0);
  const activeModelMeta = MODEL_CATALOG[selectedModel];

  return (
    <div
      className={`aura-panel-3d rounded-2xl flex flex-col justify-between overflow-hidden relative select-none ${
        expanded ? 'w-full h-full p-5 sm:p-6' : 'w-80 xl:w-[340px] shrink-0 h-full p-4'
      }`}
    >
      {/* Subtle Holographic Scanlines */}
      <div className="absolute inset-0 aura-holo-scanlines z-0" />

      {/* Top 3D Core Header */}
      <div className="relative z-10 flex items-center justify-between border-b border-white/[0.08] pb-3">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_12px_#00F0FF] animate-pulse" />
          <span className="text-xs font-bold tracking-[0.18em] uppercase text-cyan-300 aura-text-glow-cyan">
            3D Neural Core
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-400/30">
            60 FPS 3D
          </span>
          <button
            type="button"
            onClick={handleResetView}
            title="Reset 3D Camera Orbit"
            className="p-1 rounded-lg bg-white/[0.05] hover:bg-white/[0.12] text-white/60 hover:text-cyan-300 transition-colors cursor-pointer"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      </div>

      {/* Interactive 3D Canvas Viewport */}
      <div className="relative flex-1 min-h-[210px] flex items-center justify-center my-2">
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          className="w-full h-full cursor-grab active:cursor-grabbing"
        />

        {/* Floating 3D Corner HUD Overlays */}
        <div className="absolute top-2 left-2 pointer-events-none flex flex-col gap-1">
          <div className="px-2 py-0.5 rounded bg-black/50 border border-cyan-400/25 text-[10px] font-mono text-cyan-300 backdrop-blur-md">
            STATE: {isStreaming ? 'HYPER-STREAMING' : voiceState.toUpperCase()}
          </div>
          {wakeWordEnabled && (
            <div className="px-2 py-0.5 rounded bg-black/50 border border-emerald-400/25 text-[10px] font-mono text-emerald-300 backdrop-blur-md">
              WAKE: &quot;HEY AURA&quot; ON
            </div>
          )}
        </div>

        <div className="absolute top-2 right-2 pointer-events-none text-right">
          <div className="px-2.5 py-1 rounded-lg bg-black/60 border border-cyan-400/30 backdrop-blur-md shadow-[0_0_15px_rgba(0,240,255,0.15)]">
            <div className="text-[9px] font-mono text-white/40 uppercase">Velocity</div>
            <div className="text-xs font-bold font-mono text-cyan-300">
              {liveTps.toFixed(1)} <span className="text-[10px] text-cyan-400/80">tok/s</span>
            </div>
          </div>
        </div>

        <div className="absolute bottom-1 inset-x-0 text-center pointer-events-none">
          <span className="text-[10px] font-mono text-white/35 bg-black/40 px-2.5 py-0.5 rounded-full border border-white/[0.06]">
            {interactiveHint}
          </span>
        </div>
      </div>

      {/* 3D Spatial Telemetry & Model Engine Controls */}
      <div className="relative z-10 space-y-2.5 pt-2 border-t border-white/[0.08]">
        {/* 3D Model Selector Card */}
        <div className="aura-card-3d rounded-xl p-2.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-white/50 flex items-center gap-1">
              <Sparkles size={11} className="text-cyan-400" />
              Active Neural Engine
            </span>
            <span className="text-[10px] font-mono text-emerald-400">
              {activeModelMeta.context}
            </span>
          </div>

          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value as AuraModelId)}
            className="w-full bg-[#090B14] border border-cyan-400/30 rounded-lg px-2.5 py-1.5 text-xs font-medium text-white focus:outline-none focus:border-cyan-400 cursor-pointer"
          >
            {Object.entries(MODEL_CATALOG).map(([id, meta]) => (
              <option key={id} value={id}>
                {meta.label}
              </option>
            ))}
          </select>

          <p className="text-[10px] text-white/45 mt-1.5 leading-snug">
            {activeModelMeta.desc}
          </p>
        </div>

        {/* 3D Telemetry Grid (TPS, Context RRF, VRAM) */}
        <div className="grid grid-cols-2 gap-2">
          <div className="aura-card-3d rounded-xl p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-[10px] text-white/45 font-mono">
              <span>PEAK SPEED</span>
              <Zap size={12} className="text-amber-400" />
            </div>
            <div className="mt-1">
              <span className="text-sm font-bold font-mono text-white">
                {peakTps.toFixed(1)}
              </span>
              <span className="text-[10px] font-mono text-amber-300 ml-1">TPS</span>
            </div>
            <span className="text-[9px] text-emerald-400/80 font-mono">
              FlashAttn + Q4_0 KV
            </span>
          </div>

          <div className="aura-card-3d rounded-xl p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-[10px] text-white/45 font-mono">
              <span>CONTEXT RRF</span>
              <Database size={12} className="text-cyan-400" />
            </div>
            <div className="mt-1">
              <span className="text-xs font-bold font-mono text-cyan-300 truncate block">
                {contextWindowLabel}
              </span>
            </div>
            <span className="text-[9px] text-purple-300/80 font-mono">
              BM25 + 64d Vector
            </span>
          </div>
        </div>

        {/* Quick 3D Voice & Hardware Bar */}
        <div className="flex items-center justify-between gap-2 pt-1">
          <button
            type="button"
            onClick={triggerManualVoice}
            className={`aura-btn-3d flex-1 py-2 px-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer ${
              isMicActive || voiceState === 'listening'
                ? 'bg-cyan-400 text-black shadow-[0_0_20px_#00F0FF]'
                : 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 border border-cyan-400/35 text-cyan-200 hover:border-cyan-400'
            }`}
          >
            <Mic size={13} />
            <span>{isMicActive ? 'Listening...' : 'Speak to 3D Core'}</span>
          </button>

          <div className="px-2.5 py-2 rounded-xl bg-white/[0.03] border border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-white/70">
            <Cpu size={12} className="text-cyan-400" />
            <span>{vramGB}/{totalGB}G</span>
          </div>
        </div>

        {expanded && (
          <div className="grid grid-cols-3 gap-2 pt-2">
            <div className="aura-card-3d rounded-xl p-2.5 flex items-center gap-2 text-xs text-white/70">
              <Layers size={14} className="text-cyan-400 shrink-0" />
              <div>
                <div className="font-semibold text-white text-[11px]">Sandwich Context</div>
                <div className="text-[10px] text-white/45">Zero Lost-in-the-Middle</div>
              </div>
            </div>
            <div className="aura-card-3d rounded-xl p-2.5 flex items-center gap-2 text-xs text-white/70">
              <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
              <div>
                <div className="font-semibold text-white text-[11px]">Coreference Engine</div>
                <div className="text-[10px] text-white/45">Pronoun Entity Anchor</div>
              </div>
            </div>
            <div className="aura-card-3d rounded-xl p-2.5 flex items-center gap-2 text-xs text-white/70">
              <Sparkles size={14} className="text-purple-400 shrink-0" />
              <div>
                <div className="font-semibold text-white text-[11px]">10M Episodic Archive</div>
                <div className="text-[10px] text-white/45">Zero-Loss Compression</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

import { useEffect, useRef, useState, type ReactNode, type MouseEvent } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';

interface Tilt3DCardProps {
  children: ReactNode;
  className?: string;
  intensity?: number;
  glareColor?: string;
}

/**
 * Interactive 3D Spatial Card with real-time mouse-tracked 3D rotation
 * and holographic specular glare overlay.
 */
export const Tilt3DCard = ({
  children,
  className = '',
  intensity = 8,
  glareColor = 'rgba(0, 240, 255, 0.14)'
}: Tilt3DCardProps) => {
  const ref = useRef<HTMLDivElement | null>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const [glarePos, setGlarePos] = useState({ x: 50, y: 50, opacity: 0 });

  const springConfig = { damping: 20, stiffness: 260, mass: 0.6 };
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [intensity, -intensity]), springConfig);
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-intensity, intensity]), springConfig);

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const normX = (e.clientX - rect.left) / rect.width - 0.5;
    const normY = (e.clientY - rect.top) / rect.height - 0.5;
    x.set(normX);
    y.set(normY);
    setGlarePos({
      x: ((e.clientX - rect.left) / rect.width) * 100,
      y: ((e.clientY - rect.top) / rect.height) * 100,
      opacity: 1
    });
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
    setGlarePos((prev) => ({ ...prev, opacity: 0 }));
  };

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        rotateX,
        rotateY,
        transformStyle: 'preserve-3d'
      }}
      whileHover={{ scale: 1.012, z: 14 }}
      transition={{ type: 'spring', stiffness: 300, damping: 22 }}
      className={`relative ${className}`}
    >
      {/* Dynamic Cursor-Tracked Specular 3D Glare */}
      <div
        style={{
          background: `radial-gradient(circle 180px at ${glarePos.x}% ${glarePos.y}%, ${glareColor}, transparent 80%)`,
          opacity: glarePos.opacity,
          transition: 'opacity 0.25s ease'
        }}
        className="pointer-events-none absolute inset-0 rounded-[inherit] z-20"
      />
      {children}
    </motion.div>
  );
};

interface MiniNeuralOrb3DProps {
  size?: number;
  active?: boolean;
  colorMode?: 'cyan' | 'purple' | 'emerald';
}

/**
 * Live 60FPS 3D Spinning Geodesic Orb & Gyroscope Ring Canvas
 * Embeddable inside headers, hero banners, and voice buttons.
 */
export const MiniNeuralOrb3D = ({
  size = 84,
  active = false,
  colorMode = 'cyan'
}: MiniNeuralOrb3DProps) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    let animId: number;
    let t = 0;

    // Generate 56 Fibonacci sphere points
    const pts: { x: number; y: number; z: number }[] = [];
    const n = 56;
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      const y = 1 - (i / (n - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const theta = golden * i;
      pts.push({ x: Math.cos(theta) * r, y, z: Math.sin(theta) * r });
    }

    const rgb =
      colorMode === 'purple'
        ? '168, 85, 247'
        : colorMode === 'emerald'
        ? '16, 185, 129'
        : '0, 240, 255';

    const render = () => {
      ctx.clearRect(0, 0, size, size);
      const cx = size / 2;
      const cy = size / 2;
      const radius = size * 0.32;

      t += active ? 0.045 : 0.02;

      // Radial core glow
      const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, radius * 1.45);
      grad.addColorStop(0, `rgba(${rgb}, 0.45)`);
      grad.addColorStop(0.6, `rgba(168, 85, 247, 0.15)`);
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.45, 0, Math.PI * 2);
      ctx.fill();

      // Outer 3D tilted gyroscope ring
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(t * 0.7);
      ctx.strokeStyle = `rgba(${rgb}, 0.55)`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.ellipse(0, 0, radius * 1.28, radius * 0.48, 0, 0, Math.PI * 2);
      ctx.stroke();

      ctx.rotate(-t * 1.3);
      ctx.strokeStyle = 'rgba(168, 85, 247, 0.45)';
      ctx.beginPath();
      ctx.ellipse(0, 0, radius * 1.18, radius * 0.42, 0.8, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // Rotate and project 3D sphere nodes
      const cosY = Math.cos(t);
      const sinY = Math.sin(t);
      const cosX = Math.cos(t * 0.6);
      const sinX = Math.sin(t * 0.6);

      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        const pulse = active ? 1 + 0.12 * Math.sin(t * 3 + i) : 1;
        const x1 = p.x * pulse * cosY - p.z * pulse * sinY;
        const z1 = p.x * pulse * sinY + p.z * pulse * cosY;
        const y2 = p.y * pulse * cosX - z1 * sinX;
        const z2 = p.y * pulse * sinX + z1 * cosX;

        const persp = 2.8 / (2.8 + z2);
        const sx = cx + x1 * radius * persp;
        const sy = cy + y2 * radius * persp;
        const alpha = Math.max(0.2, (1.4 - z2) * 0.65);

        ctx.fillStyle = z2 < -0.2 ? `rgba(255,255,255,${alpha})` : `rgba(${rgb},${alpha})`;
        ctx.beginPath();
        ctx.arc(sx, sy, Math.max(1.0, (size / 42) * persp), 0, Math.PI * 2);
        ctx.fill();
      }

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [size, active, colorMode]);

  return <canvas ref={canvasRef} style={{ width: size, height: size }} className="shrink-0" />;
};

/**
 * Live fluctuating telemetry number hook for dynamic sci-fi HUD feel.
 */
export const useDynamicTelemetry = (baseValue: number, variance: number, intervalMs = 1400) => {
  const [val, setVal] = useState(baseValue);

  useEffect(() => {
    setVal(baseValue);
  }, [baseValue]);

  useEffect(() => {
    const id = window.setInterval(() => {
      const delta = (Math.random() - 0.48) * variance;
      setVal((prev) => Number(Math.max(1, prev + delta * 0.35 + (baseValue - prev) * 0.4).toFixed(1)));
    }, intervalMs);
    return () => clearInterval(id);
  }, [baseValue, variance, intervalMs]);

  return val;
};

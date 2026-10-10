import { useEffect, useRef } from 'react';
import { useVoiceStore } from '../../store/voiceStore';
import { useChatStore } from '../../store/chatStore';

interface StarNode3D {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  color: string;
  size: number;
}

export const Ambient3DScene = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { voiceState, wakeWordStatus, isMicActive } = useVoiceStore();
  const { isStreaming } = useChatStore();
  const mouseRef = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let time = 0;

    const colors = ['#00F0FF', '#A855F7', '#10B981', '#38BDF8'];
    const numNodes = 95;
    const nodes: StarNode3D[] = [];

    for (let i = 0; i < numNodes; i++) {
      nodes.push({
        x: (Math.random() - 0.5) * 3.2,
        y: (Math.random() - 0.5) * 2.2,
        z: Math.random() * 3.5 + 0.2,
        vx: (Math.random() - 0.5) * 0.0015,
        vy: (Math.random() - 0.5) * 0.0015,
        vz: -(Math.random() * 0.006 + 0.002),
        color: colors[i % colors.length],
        size: Math.random() * 2.0 + 0.8
      });
    }

    const handleResize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current.targetX = (e.clientX / window.innerWidth - 0.5) * 2;
      mouseRef.current.targetY = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);

    const render = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const cx = w / 2;
      const cy = h / 2;

      ctx.clearRect(0, 0, w, h);

      const isActiveAudio =
        voiceState === 'speaking' ||
        voiceState === 'listening' ||
        wakeWordStatus === 'capturing' ||
        isMicActive;

      const speedBoost = isStreaming ? 3.2 : isActiveAudio ? 2.4 : 1.0;
      time += 0.015 * speedBoost;

      // Smooth camera parallax interpolation
      mouseRef.current.x += (mouseRef.current.targetX - mouseRef.current.x) * 0.06;
      mouseRef.current.y += (mouseRef.current.targetY - mouseRef.current.y) * 0.06;

      const camX = mouseRef.current.x * 0.35;
      const camY = mouseRef.current.y * 0.25;

      // 1. Draw 3D Rotating Holographic Gyroscope Rings in Deep Background
      const ringRadius = Math.min(w, h) * 0.38;
      ctx.save();
      ctx.translate(cx - camX * 45, cy - camY * 45);

      for (let r = 0; r < 3; r++) {
        const angleOffset = time * (r % 2 === 0 ? 0.35 : -0.25) + r * 1.1;
        const rx = ringRadius * (0.65 + r * 0.22);
        const ry = rx * (0.38 + 0.15 * Math.sin(time * 0.5 + r));

        ctx.save();
        ctx.rotate(angleOffset);
        ctx.strokeStyle =
          r === 0
            ? 'rgba(0, 240, 255, 0.07)'
            : r === 1
            ? 'rgba(168, 85, 247, 0.06)'
            : 'rgba(16, 185, 129, 0.05)';
        ctx.lineWidth = 1.2;
        ctx.setLineDash([12, 18]);
        ctx.beginPath();
        ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
      ctx.restore();

      // 2. Project & Advance 3D Volumetric Nodes
      const fov = 1.8;
      const scale = Math.max(w, h) * 0.55;
      const projected: { sx: number; sy: number; z: number; color: string; r: number }[] = [];

      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        n.x += n.vx * speedBoost;
        n.y += n.vy * speedBoost;
        n.z += n.vz * speedBoost;

        // Respawn in deep 3D space when passing camera
        if (n.z <= 0.15) {
          n.z = 3.6;
          n.x = (Math.random() - 0.5) * 3.2;
          n.y = (Math.random() - 0.5) * 2.2;
        }

        const relX = n.x - camX * (1.2 / n.z);
        const relY = n.y - camY * (1.2 / n.z);
        const persp = fov / n.z;

        const sx = cx + relX * scale * persp * 0.5;
        const sy = cy + relY * scale * persp * 0.5;

        if (sx >= -50 && sx <= w + 50 && sy >= -50 && sy <= h + 50) {
          projected.push({
            sx,
            sy,
            z: n.z,
            color: n.color,
            r: Math.min(4.2, n.size * persp * 0.85)
          });
        }
      }

      // 3. Draw 3D Constellation Synaptic Web between close particles
      const maxDistSq = 135 * 135;
      ctx.lineWidth = 0.65;
      for (let i = 0; i < projected.length; i++) {
        const p1 = projected[i];
        for (let j = i + 1; j < projected.length; j++) {
          const p2 = projected[j];
          const dx = p1.sx - p2.sx;
          const dy = p1.sy - p2.sy;
          const dSq = dx * dx + dy * dy;
          if (dSq < maxDistSq && Math.abs(p1.z - p2.z) < 0.85) {
            const alpha = (1 - dSq / maxDistSq) * Math.max(0.04, (3.6 - p1.z) / 3.6) * 0.22;
            ctx.strokeStyle = `rgba(0, 240, 255, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(p1.sx, p1.sy);
            ctx.lineTo(p2.sx, p2.sy);
            ctx.stroke();
          }
        }
      }

      // 4. Draw 3D Particles with Z-Depth Glow
      for (let i = 0; i < projected.length; i++) {
        const p = projected[i];
        const depthAlpha = Math.min(0.85, Math.max(0.12, (3.7 - p.z) / 3.2));
        ctx.fillStyle = p.color;
        ctx.globalAlpha = depthAlpha;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1.0;

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, [voiceState, wakeWordStatus, isMicActive, isStreaming]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-screen h-screen pointer-events-none z-0"
    />
  );
};

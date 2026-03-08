"use client";

import { useRef, useMemo } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

interface ParticleEdgeProps {
  position: "top" | "bottom";
}

const PARTICLE_COUNT = 1500;
const MAX_DIST = 1.4;
const HALF_WIDTH = 4.5;

interface ShardData {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  rotation: number;
  rotSpeed: number;
  baseScale: number;
  driftOffset: number;
}

function randomScale(): number {
  const t = Math.random();
  // 70% regular, 30% small
  return t > 0.7
    ? 0.015 + Math.random() * 0.025
    : 0.04 + Math.random() * 0.08;
}

function spawnParticle(dir: number, scattered: boolean): ShardData {
  // If scattered, place throughout the field (for initial fill)
  // If not, spawn right at the edge (for recycling)
  const dist = scattered
    ? Math.pow(Math.random(), 0.3) * MAX_DIST
    : (Math.random() - 0.5) * 0.15;

  return {
    x: (Math.random() - 0.5) * HALF_WIDTH * 2.2,
    y: dir * dist,
    z: (Math.random() - 0.5) * 0.3,
    vx: (Math.random() - 0.5) * 0.0015,
    vy: dir * (0.001 + Math.random() * 0.002),
    vz: (Math.random() - 0.5) * 0.001,
    rotation: Math.random() * Math.PI * 2,
    rotSpeed: (Math.random() - 0.5) * 0.0025,
    baseScale: randomScale(),
    driftOffset: Math.random() * Math.PI * 2,
  };
}

function Shards({ position }: { position: "top" | "bottom" }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const { viewport } = useThree();
  const dir = position === "top" ? 1 : -1;

  const { geometry, particles } = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const vertices = new Float32Array([
      -0.5, -0.5, 0,
       0.7, -0.3, 0,
       0.4,  0.6, 0,
      -0.3,  0.4, 0,
    ]);
    geo.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
    geo.setIndex([0, 1, 2, 0, 2, 3]);
    geo.computeVertexNormals();

    // Initial fill: scatter particles across the field
    const data: ShardData[] = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      data.push(spawnParticle(dir, true));
    }
    return { geometry: geo, particles: data };
  }, [dir]);

  const dummy = useMemo(() => new THREE.Object3D(), []);

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const time = clock.getElapsedTime();

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const p = particles[i];

      // Sine wave lateral drift
      const driftX = Math.sin(time * 0.3 + p.driftOffset) * 0.00015;
      const driftY = Math.cos(time * 0.2 + p.driftOffset) * 0.0001;

      // Move
      p.x += p.vx + driftX;
      p.y += p.vy + driftY;
      p.z += p.vz;
      p.rotation += p.rotSpeed;

      // Distance from edge
      const yDist = Math.abs(p.y);

      // Recycle when too far
      if (yDist > MAX_DIST || Math.abs(p.x) > HALF_WIDTH * 1.1) {
        const fresh = spawnParticle(dir, false);
        p.x = fresh.x;
        p.y = fresh.y;
        p.z = fresh.z;
        p.vx = fresh.vx;
        p.vy = fresh.vy;
        p.vz = fresh.vz;
        p.rotation = fresh.rotation;
        p.rotSpeed = fresh.rotSpeed;
        p.baseScale = fresh.baseScale;
        p.driftOffset = fresh.driftOffset;
      }

      // Scale down as they drift farther
      const distanceFade = Math.max(0, 1 - yDist / MAX_DIST);

      dummy.position.set(p.x, p.y, p.z);
      dummy.rotation.set(0, 0, p.rotation);
      dummy.scale.setScalar(p.baseScale * distanceFade);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }

    meshRef.current.instanceMatrix.needsUpdate = true;
  });

  const scaleX = Math.max(1, viewport.width / 9);

  return (
    <group scale={[scaleX, 1, 1]}>
      <instancedMesh ref={meshRef} args={[geometry, undefined, PARTICLE_COUNT]}>
        <meshBasicMaterial color="#C43B3B" side={THREE.DoubleSide} transparent opacity={0.2} depthWrite={false} />
      </instancedMesh>
    </group>
  );
}

export function ParticleEdge({ position }: ParticleEdgeProps) {
  const isTop = position === "top";
  const CANVAS_HEIGHT = 150;

  return (
    <div
      className="pointer-events-none absolute inset-x-0"
      style={{
        height: CANVAS_HEIGHT,
        [isTop ? "top" : "bottom"]: -(CANVAS_HEIGHT * 0.45),
        clipPath: isTop ? "inset(0 0 55% 0)" : "inset(55% 0 0 0)",
      }}
      aria-hidden="true"
    >
      <Canvas
        camera={{ position: [0, 0, 8], fov: 30 }}
        style={{ width: "100%", height: "100%" }}
        gl={{ alpha: true, antialias: true }}
      >
        <Shards position={position} />
      </Canvas>
    </div>
  );
}

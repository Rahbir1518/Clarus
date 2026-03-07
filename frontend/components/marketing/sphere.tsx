"use client";

import { useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment, MeshDistortMaterial } from "@react-three/drei";
import type { Mesh } from "three";

function FloatingSphere() {
  const meshRef = useRef<Mesh>(null);
  const { viewport } = useThree();

  // Scale sphere based on viewport width: ~0.6 on mobile, 1.0 on desktop
  const scale = Math.min(1, Math.max(0.6, viewport.width / 8));

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const t = clock.getElapsedTime();
    meshRef.current.rotation.y = t * 0.15;
    meshRef.current.rotation.x = Math.sin(t * 0.3) * 0.05;
    meshRef.current.position.y = Math.sin(t * 0.5) * 0.15;
    meshRef.current.position.x = Math.cos(t * 0.4) * 0.03;

    // Gentle squash/stretch into ovals and abstract shapes
    meshRef.current.scale.x = scale * (1 + Math.sin(t * 0.4) * 0.08);
    meshRef.current.scale.y = scale * (1 + Math.sin(t * 0.3 + 1.5) * 0.08);
    meshRef.current.scale.z = scale * (1 + Math.cos(t * 0.35 + 3.0) * 0.06);
  });

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[1.2, 128, 128]} />
      <MeshDistortMaterial
        color="#faf0f0"
        roughness={0.1}
        metalness={0.05}
        clearcoat={1}
        clearcoatRoughness={0.05}
        distort={0.3}
        speed={1.5}
        envMapIntensity={1.2}
      />
    </mesh>
  );
}

export function Sphere3D() {
  return (
    <div
      className="pointer-events-none absolute inset-0 max-md:opacity-40"
      aria-hidden="true"
    >
      <Canvas
        camera={{ position: [0, 0, 4.5], fov: 45 }}
        style={{ width: "100%", height: "100%" }}
        gl={{ alpha: true, antialias: true }}
      >
        {/* Warm red-tinted lighting */}
        <ambientLight intensity={0.4} color="#fff5f5" />
        <directionalLight
          position={[5, 5, 5]}
          intensity={0.8}
          color="#ffe0e0"
        />
        <directionalLight
          position={[-3, -2, 4]}
          intensity={0.3}
          color="#fff0f0"
        />

        {/* Offset sphere to center-right */}
        <group position={[1.5, 0, 0]}>
          <FloatingSphere />
        </group>

        <Environment preset="studio" />
      </Canvas>
    </div>
  );
}

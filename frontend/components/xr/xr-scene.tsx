"use client";

import { useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, RoundedBox, Text } from "@react-three/drei";
import { XR, type XRStore } from "@react-three/xr";
import type { XRStep } from "@/components/xr/xr-data";

const BOLD = "/fonts/VeraBd.ttf";
const REGULAR = "/fonts/Vera.ttf";

interface CardProps {
  step: XRStep;
  position: [number, number, number];
  rotationY: number;
  selected: boolean;
  onSelect: () => void;
}

function StepCard({ step, position, rotationY, selected, onSelect }: CardProps) {
  const [hover, setHover] = useState(false);
  const lift = selected ? 0.12 : hover ? 0.05 : 0;
  return (
    <group position={[position[0], position[1] + lift, position[2]]} rotation={[0, rotationY, 0]}>
      <RoundedBox
        args={[0.72, 0.44, 0.02]}
        radius={0.03}
        smoothness={4}
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
        onPointerOver={() => setHover(true)}
        onPointerOut={() => setHover(false)}
      >
        <meshStandardMaterial
          color={selected ? "#2a2c48" : "#181a28"}
          roughness={0.6}
          metalness={0.1}
        />
      </RoundedBox>
      <mesh position={[-0.345, 0, 0.012]}>
        <planeGeometry args={[0.02, 0.4]} />
        <meshBasicMaterial color={step.color} />
      </mesh>
      <Text
        font={BOLD}
        position={[-0.3, 0.15, 0.015]}
        fontSize={0.05}
        color={step.color}
        anchorX="left"
        anchorY="middle"
      >
        {`STEP ${step.order}`}
      </Text>
      <Text
        font={BOLD}
        position={[-0.3, 0.03, 0.015]}
        fontSize={0.045}
        maxWidth={0.6}
        lineHeight={1.15}
        color="#eef0f7"
        anchorX="left"
        anchorY="middle"
      >
        {step.title}
      </Text>
      <Text
        font={REGULAR}
        position={[-0.3, -0.15, 0.015]}
        fontSize={0.03}
        color="#a3a9be"
        anchorX="left"
        anchorY="middle"
      >
        {`${step.time} · ${step.phase}`}
      </Text>
      {step.status ? (
        <Text
          font={BOLD}
          position={[0.3, 0.15, 0.015]}
          fontSize={0.03}
          color={
            step.status === "done" ? "#3fd1bd" : step.status === "extra" ? "#a3a9be" : "#f5a65b"
          }
          anchorX="right"
          anchorY="middle"
        >
          {step.status === "done" ? "DONE" : step.status === "extra" ? "EXTRA" : "OUT OF ORDER"}
        </Text>
      ) : null}
    </group>
  );
}

export default function XRScene({
  steps,
  title,
  store,
  onSelect,
  selected,
}: {
  steps: XRStep[];
  title: string;
  store: XRStore;
  onSelect: (order: number) => void;
  selected: number | null;
}) {
  // Cards on an arc around the viewer: comfortable to read in a headset, and in a browser.
  const layout = useMemo(() => {
    const perRow = Math.min(7, Math.max(3, Math.ceil(steps.length / 2)));
    const radius = 2.2;
    const spread = Math.min(Math.PI * 0.75, perRow * 0.3);
    return steps.map((s, i) => {
      const row = Math.floor(i / perRow);
      const col = i % perRow;
      const count = Math.min(perRow, steps.length - row * perRow);
      const a = count > 1 ? -spread / 2 + (spread * col) / (count - 1) : 0;
      return {
        step: s,
        position: [Math.sin(a) * radius, 1.75 - row * 0.55, -Math.cos(a) * radius] as [
          number,
          number,
          number,
        ],
        rotationY: -a,
      };
    });
  }, [steps]);

  return (
    <Canvas camera={{ position: [0, 1.55, -0.2], fov: 62 }} dpr={[1, 2]}>
      <XR store={store}>
        <color attach="background" args={["#0b0c12"]} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[2, 4, 2]} intensity={1.2} />
        <Text
          font={BOLD}
          position={[0, 2.55, -2.1]}
          fontSize={0.11}
          color="#eef0f7"
          anchorX="center"
          maxWidth={3}
        >
          {title}
        </Text>
        <Text
          font={REGULAR}
          position={[0, 2.38, -2.1]}
          fontSize={0.05}
          color="#a3a9be"
          anchorX="center"
        >
          Replay · action steps
        </Text>
        {layout.map(({ step, position, rotationY }) => (
          <StepCard
            key={step.order}
            step={step}
            position={position}
            rotationY={rotationY}
            selected={selected === step.order}
            onSelect={() => onSelect(step.order)}
          />
        ))}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
          <circleGeometry args={[4, 48]} />
          <meshStandardMaterial color="#13151f" />
        </mesh>
        <OrbitControls
          target={[0, 1.45, -1.4]}
          enablePan={false}
          minDistance={0.5}
          maxDistance={4}
        />
      </XR>
    </Canvas>
  );
}

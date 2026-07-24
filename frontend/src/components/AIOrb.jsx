import { useRef, useMemo, useState, useEffect, Component } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Float, MeshDistortMaterial, Environment } from '@react-three/drei'
import * as THREE from 'three'

/* ================================================================
   Orb State Presets — distinct visual profiles per AI state
   ================================================================

   idle       → slow breathing, gentle shimmer
   listening  → rhythmic pulse (like a heartbeat), cyan tint
   thinking   → faster distortion + golden emissive
   responding → smooth fast flow, bright purple glow
*/

const ORB_PRESETS = {
  idle: {
    distort: 0.15, distortAmplitude: 0.04, distortFreq: 0.8,
    speed: 1.8, rotSpeed: 0.08,
    glowOpacity: 0.05, glowScale: 1.2, glowPulseAmp: 0.02, glowPulseFreq: 0.7,
    emissive: '#6d5acf', emissiveIntensity: 0.3,
    particleSpeed: 0.08, particleSize: 0.02, particleOpacity: 0.35,
    floatSpeed: 1, floatIntensity: 0.4, rotationIntensity: 0.08,
    lightColor1: '#a78bfa', lightColor2: '#3b82f6',
    // Breathing: slow scale oscillation
    breatheAmp: 0.03, breatheFreq: 0.5,
  },
  listening: {
    distort: 0.22, distortAmplitude: 0.06, distortFreq: 2.5,
    speed: 3, rotSpeed: 0.12,
    glowOpacity: 0.1, glowScale: 1.3, glowPulseAmp: 0.06, glowPulseFreq: 2,
    emissive: '#38bdf8', emissiveIntensity: 0.5,
    particleSpeed: 0.25, particleSize: 0.03, particleOpacity: 0.6,
    floatSpeed: 2, floatIntensity: 0.8, rotationIntensity: 0.15,
    lightColor1: '#38bdf8', lightColor2: '#a78bfa',
    breatheAmp: 0.05, breatheFreq: 1.8,
  },
  thinking: {
    distort: 0.3, distortAmplitude: 0.12, distortFreq: 3.5,
    speed: 5, rotSpeed: 0.2,
    glowOpacity: 0.1, glowScale: 1.32, glowPulseAmp: 0.07, glowPulseFreq: 2.5,
    emissive: '#f59e0b', emissiveIntensity: 0.5,
    particleSpeed: 0.35, particleSize: 0.035, particleOpacity: 0.7,
    floatSpeed: 2.5, floatIntensity: 1, rotationIntensity: 0.25,
    lightColor1: '#f59e0b', lightColor2: '#a78bfa',
    breatheAmp: 0.04, breatheFreq: 2.2,
  },
  responding: {
    distort: 0.35, distortAmplitude: 0.15, distortFreq: 4,
    speed: 6, rotSpeed: 0.15,
    glowOpacity: 0.14, glowScale: 1.38, glowPulseAmp: 0.08, glowPulseFreq: 3,
    emissive: '#a78bfa', emissiveIntensity: 0.6,
    particleSpeed: 0.4, particleSize: 0.04, particleOpacity: 0.8,
    floatSpeed: 3, floatIntensity: 1.2, rotationIntensity: 0.3,
    lightColor1: '#a78bfa', lightColor2: '#6d5acf',
    breatheAmp: 0.03, breatheFreq: 3,
  },
}

function getPreset(orbState) {
  return ORB_PRESETS[orbState] || ORB_PRESETS.idle
}

/* ================================================================
   Smooth lerp helper — interpolates a ref toward a target
   ================================================================ */

function lerpTo(current, target, delta, lerpSpeed = 3) {
  return current + (target - current) * Math.min(delta * lerpSpeed, 1)
}

/* ================================================================
   Inner Orb Sphere — the main glowing AI sphere
   ================================================================ */

function OrbCore({ orbState = 'idle' }) {
  const meshRef = useRef()
  const materialRef = useRef()
  const currentDistort = useRef(0.15)
  const currentSpeed = useRef(1.8)
  const currentScale = useRef(1)

  useFrame((state, delta) => {
    const p = getPreset(orbState)
    const t = state.clock.elapsedTime

    if (meshRef.current) {
      meshRef.current.rotation.y += delta * p.rotSpeed
      meshRef.current.rotation.x = Math.sin(t * 0.3) * 0.1

      // Breathing scale
      const breathe = 1 + Math.sin(t * p.breatheFreq * Math.PI * 2) * p.breatheAmp
      currentScale.current = lerpTo(currentScale.current, breathe, delta, 4)
      meshRef.current.scale.setScalar(currentScale.current)
    }

    if (materialRef.current) {
      const targetDistort = p.distort + Math.sin(t * p.distortFreq) * p.distortAmplitude
      currentDistort.current = lerpTo(currentDistort.current, targetDistort, delta, 3)
      currentSpeed.current = lerpTo(currentSpeed.current, p.speed, delta, 2)

      materialRef.current.distort = currentDistort.current
      materialRef.current.speed = currentSpeed.current
      materialRef.current.emissiveIntensity = p.emissiveIntensity
    }
  })

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[1, 48, 48]} />
      <MeshDistortMaterial
        ref={materialRef}
        color="#a78bfa"
        emissive="#6d5acf"
        emissiveIntensity={0.3}
        roughness={0.15}
        metalness={0.8}
        distort={0.15}
        speed={1.8}
        transparent
        opacity={0.92}
      />
    </mesh>
  )
}

/* ================================================================
   Outer Glow Shell — translucent halo around the orb
   ================================================================ */

function OrbGlow({ orbState = 'idle' }) {
  const meshRef = useRef()
  const currentScale = useRef(1.2)
  const currentOpacity = useRef(0.05)

  useFrame((state, delta) => {
    const p = getPreset(orbState)
    const t = state.clock.elapsedTime

    if (meshRef.current) {
      const targetScale = p.glowScale + Math.sin(t * p.glowPulseFreq) * p.glowPulseAmp
      currentScale.current = lerpTo(currentScale.current, targetScale, delta, 3)
      meshRef.current.scale.setScalar(currentScale.current)
      meshRef.current.rotation.y -= 0.003

      // Smooth opacity transition
      currentOpacity.current = lerpTo(currentOpacity.current, p.glowOpacity, delta, 2)
      meshRef.current.material.opacity = currentOpacity.current
      meshRef.current.material.emissiveIntensity = p.emissiveIntensity
    }
  })

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[1, 32, 32]} />
      <meshStandardMaterial
        color="#a78bfa"
        emissive="#7c3aed"
        emissiveIntensity={0.25}
        transparent
        opacity={0.05}
        side={THREE.BackSide}
        depthWrite={false}
      />
    </mesh>
  )
}

/* ================================================================
   Particle Ring — orbiting particles around the sphere
   ================================================================ */

function ParticleRing({ count = 32, orbState = 'idle' }) {
  const pointsRef = useRef()
  const matRef = useRef()
  const currentSize = useRef(0.02)

  const particleData = useMemo(() => {
    const positions = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2
      const radius = 1.6 + Math.random() * 0.3
      positions[i * 3] = Math.cos(angle) * radius
      positions[i * 3 + 1] = (Math.random() - 0.5) * 0.4
      positions[i * 3 + 2] = Math.sin(angle) * radius
    }
    return { positions }
  }, [count])

  useFrame((state, delta) => {
    const p = getPreset(orbState)
    if (pointsRef.current) {
      pointsRef.current.rotation.y += p.particleSpeed * 0.01
      pointsRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.5) * 0.1
    }
    if (matRef.current) {
      currentSize.current = lerpTo(currentSize.current, p.particleSize, delta, 3)
      matRef.current.size = currentSize.current
      matRef.current.opacity = p.particleOpacity
    }
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={particleData.positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        ref={matRef}
        size={0.02}
        color="#a78bfa"
        transparent
        opacity={0.35}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

/* ================================================================
   Scene Composition
   ================================================================ */

function OrbScene({ orbState = 'idle' }) {
  const p = getPreset(orbState)
  return (
    <>
      <ambientLight intensity={0.2} />
      <pointLight position={[5, 5, 5]} intensity={0.8} color={p.lightColor1} />
      <pointLight position={[-5, -3, 3]} intensity={0.4} color={p.lightColor2} />

      <Float
        speed={p.floatSpeed}
        rotationIntensity={p.rotationIntensity}
        floatIntensity={p.floatIntensity}
        floatingRange={[-0.1, 0.1]}
      >
        <OrbGlow orbState={orbState} />
        <OrbCore orbState={orbState} />
        <ParticleRing orbState={orbState} />
      </Float>

      <Environment preset="night" />
    </>
  )
}

/* ================================================================
   CSS Fallback — used when WebGL is unavailable or crashes
   ================================================================ */

const FALLBACK_COLORS = {
  idle:       { glow: 'rgba(167, 139, 250, 0.25)', speed: '4s' },
  listening:  { glow: 'rgba(56, 189, 248, 0.4)',   speed: '1.5s' },
  thinking:   { glow: 'rgba(245, 158, 11, 0.4)',   speed: '1s' },
  responding: { glow: 'rgba(167, 139, 250, 0.5)',  speed: '1.2s' },
}

function CSSFallbackOrb({ orbState = 'idle', className = '', style = {} }) {
  const fb = FALLBACK_COLORS[orbState] || FALLBACK_COLORS.idle
  return (
    <div
      className={`ai-orb-fallback ai-orb-fallback--${orbState} ${className}`}
      style={{
        width: '120px',
        height: '120px',
        borderRadius: '50%',
        background: 'radial-gradient(circle at 35% 35%, #a78bfa 0%, #6d5acf 50%, #3b82f6 100%)',
        boxShadow: `0 0 50px ${fb.glow}`,
        animation: `pulse-fallback ${fb.speed} ease-in-out infinite`,
        transition: 'box-shadow 0.6s ease',
        ...style,
      }}
    />
  )
}

/* ================================================================
   Error Boundary — catches WebGL crashes at runtime
   ================================================================ */

class OrbErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    console.warn('[AIOrb] WebGL error, falling back to CSS:', error.message)
  }

  render() {
    if (this.state.hasError) {
      return <CSSFallbackOrb {...this.props} />
    }
    return this.props.children
  }
}

/* ================================================================
   Exported Component — the Canvas wrapper
   ================================================================ */

/**
 * 3D AI Orb component with multi-state animations.
 *
 * @param {Object}  props
 * @param {boolean} props.speaking  - Legacy: whether AI is active (backward compat)
 * @param {string}  props.orbState  - 'idle' | 'listening' | 'thinking' | 'responding'
 * @param {string}  props.className - Optional CSS class
 * @param {Object}  props.style     - Optional inline styles
 */
export default function AIOrb({ speaking = false, orbState, className = '', style = {} }) {
  // Resolve state: prefer explicit orbState, fall back to speaking boolean
  const resolvedState = orbState || (speaking ? 'responding' : 'idle')

  const [webglAvailable, setWebglAvailable] = useState(true)

  useEffect(() => {
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
      if (!gl) setWebglAvailable(false)
      if (gl) {
        const ext = gl.getExtension('WEBGL_lose_context')
        if (ext) ext.loseContext()
      }
    } catch {
      setWebglAvailable(false)
    }
  }, [])

  if (!webglAvailable) {
    return <CSSFallbackOrb orbState={resolvedState} className={className} style={style} />
  }

  return (
    <OrbErrorBoundary orbState={resolvedState} className={className} style={style}>
      <div
        className={`ai-orb-container ${className}`}
        style={{
          width: '180px',
          height: '180px',
          position: 'relative',
          ...style,
        }}
      >
        <Canvas
          camera={{ position: [0, 0, 3.5], fov: 45 }}
          dpr={[1, 1.5]}
          gl={{
            antialias: true,
            alpha: true,
            powerPreference: 'high-performance',
            failIfMajorPerformanceCaveat: false,
          }}
          style={{ background: 'transparent' }}
          frameloop="always"
          onCreated={({ gl: renderer }) => {
            const canvas = renderer.domElement
            canvas.addEventListener('webglcontextlost', (e) => {
              e.preventDefault()
              console.warn('[AIOrb] WebGL context lost')
            })
          }}
        >
          <OrbScene orbState={resolvedState} />
        </Canvas>
      </div>
    </OrbErrorBoundary>
  )
}

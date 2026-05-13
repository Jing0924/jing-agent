import { Suspense, useEffect, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Center, OrbitControls, useAnimations, useGLTF } from '@react-three/drei'
import type { Mesh } from 'three'
import { LoopRepeat } from 'three'

import { AVATAR_GLB_URL } from './avatar-config'
import { AvatarErrorBoundary } from './AvatarErrorBoundary'
import { lipSyncBus } from './lip-sync-bus'

/** Index helpers populated once per loaded model. */
type MorphTargets = {
  jawMesh: Mesh | null
  jawIndex: number
  blinkMeshL: Mesh | null
  blinkIndexL: number
  blinkMeshR: Mesh | null
  blinkIndexR: number
}

const EMPTY_MORPHS: MorphTargets = {
  jawMesh: null,
  jawIndex: -1,
  blinkMeshL: null,
  blinkIndexL: -1,
  blinkMeshR: null,
  blinkIndexR: -1,
}

/** Find first SkinnedMesh (Mesh subclass) that owns the requested morph name. */
function findMorph(
  root: { traverse: (cb: (obj: unknown) => void) => void },
  name: string,
): { mesh: Mesh; index: number } | null {
  let found: { mesh: Mesh; index: number } | null = null
  root.traverse((obj: unknown) => {
    if (found) return
    const m = obj as Mesh
    const dict = m?.morphTargetDictionary
    if (!dict) return
    if (!Array.isArray(m.morphTargetInfluences)) return
    const idx = dict[name]
    if (typeof idx === 'number') found = { mesh: m, index: idx }
  })
  return found
}

/**
 * Lightweight rotating placeholder while the GLB is loading or after a
 * load error. Sits inside
 * the same `<Canvas>` so the surrounding chrome never flashes.
 */
function FallbackSpinner() {
  const ref = useRef<Mesh>(null)
  useFrame((_, delta) => {
    const mesh = ref.current
    if (!mesh) return
    mesh.rotation.x += delta * 0.6
    mesh.rotation.y += delta * 0.9
  })
  return (
    <mesh ref={ref} position={[0, 0.95, 0]}>
      <icosahedronGeometry args={[0.18, 0]} />
      <meshStandardMaterial color="#94a3b8" flatShading wireframe={false} />
    </mesh>
  )
}

function Avatar({ url }: { url: string }) {
  const { scene, animations } = useGLTF(url)
  const { actions } = useAnimations(animations, scene)
  const morphsRef = useRef<MorphTargets>(EMPTY_MORPHS)
  const blinkValueRef = useRef(0)
  const blinkTargetRef = useRef(0)

  useEffect(() => {
    if (!animations.length) return

    const idleAction =
      actions['Idle'] ??
      actions['idle'] ??
      (animations[0] ? actions[animations[0].name] : undefined)
    if (!idleAction) return

    idleAction.reset().setLoop(LoopRepeat, Infinity).fadeIn(0.42).play()
    return () => {
      idleAction.fadeOut(0.32)
      idleAction.stop()
    }
  }, [animations, actions, scene])

  useEffect(() => {
    const jaw = findMorph(scene, 'jawOpen')
    const blinkL = findMorph(scene, 'eyeBlinkLeft')
    const blinkR = findMorph(scene, 'eyeBlinkRight')
    morphsRef.current = {
      jawMesh: jaw?.mesh ?? null,
      jawIndex: jaw?.index ?? -1,
      blinkMeshL: blinkL?.mesh ?? null,
      blinkIndexL: blinkL?.index ?? -1,
      blinkMeshR: blinkR?.mesh ?? null,
      blinkIndexR: blinkR?.index ?? -1,
    }
    return () => {
      morphsRef.current = EMPTY_MORPHS
    }
  }, [scene])

  // Idle blink scheduler: every 3–6s, trigger a quick close→open ramp
  // (target 1, then back to 0 ~120ms later) on both eyelid morphs.
  useEffect(() => {
    let cancelled = false
    let openTimer: ReturnType<typeof setTimeout> | null = null
    const schedule = () => {
      if (cancelled) return
      const delay = 3000 + Math.random() * 3000
      openTimer = setTimeout(() => {
        if (cancelled) return
        blinkTargetRef.current = 1
        openTimer = setTimeout(() => {
          if (cancelled) return
          blinkTargetRef.current = 0
          schedule()
        }, 120)
      }, delay)
    }
    schedule()
    return () => {
      cancelled = true
      if (openTimer) clearTimeout(openTimer)
    }
  }, [])

  useFrame((_, delta) => {
    const m = morphsRef.current

    if (m.jawMesh && m.jawIndex >= 0 && m.jawMesh.morphTargetInfluences) {
      const cur = m.jawMesh.morphTargetInfluences[m.jawIndex] ?? 0
      const target = lipSyncBus.mouth
      // ~50ms exponential smoothing at 60Hz (alpha=0.35); frame-rate
      // independent via 1 - exp(-k*delta).
      const alpha = 1 - Math.exp(-delta * 21)
      m.jawMesh.morphTargetInfluences[m.jawIndex] =
        cur + (target - cur) * alpha
    }

    // Blink ramp — quick on close (alpha 0.6), slower on open (0.15).
    const target = blinkTargetRef.current
    const cur = blinkValueRef.current
    const alpha = target > cur ? 0.6 : 0.15
    blinkValueRef.current = cur + (target - cur) * alpha
    const v = blinkValueRef.current
    if (m.blinkMeshL?.morphTargetInfluences && m.blinkIndexL >= 0) {
      m.blinkMeshL.morphTargetInfluences[m.blinkIndexL] = v
    }
    if (m.blinkMeshR?.morphTargetInfluences && m.blinkIndexR >= 0) {
      m.blinkMeshR.morphTargetInfluences[m.blinkIndexR] = v
    }
  })

  return (
    <Center position={[0, 0.7, -0.5]}>
      <primitive object={scene} />
    </Center>
  )
}

/** Remount when `url` changes so load-error state resets without an effect. */
function TalkingAvatarCanvas({ url }: { url: string }) {
  const [loadError, setLoadError] = useState<Error | null>(null)

  const hintText = loadError
    ? 'Avatar 載入失敗（URL 無效或 public 資產缺失）。請參考 frontend/README.md'
    : null

  return (
    <div className="relative h-[360px] w-full overflow-hidden rounded-md border border-border bg-muted/30">
      <Canvas
        camera={{ position: [0, 1.0, 1.35], fov: 29 }}
        dpr={[1, 2]}
      >
        <ambientLight intensity={0.7} />
        <directionalLight position={[3, 4, 5]} intensity={1.0} />
        <AvatarErrorBoundary
          onError={setLoadError}
          fallback={() => <FallbackSpinner />}
        >
          <Suspense fallback={<FallbackSpinner />}>
            <Avatar url={url} />
          </Suspense>
        </AvatarErrorBoundary>
        <OrbitControls
          target={[0, 0.95, 0]}
          enablePan={false}
          enableZoom={false}
        />
      </Canvas>
      {hintText ? (
        <p className="pointer-events-none absolute bottom-2 left-2 text-xs text-muted-foreground">
          {hintText}
        </p>
      ) : null}
    </div>
  )
}

export function TalkingAvatarPlaceholder({
  glbUrl,
}: {
  glbUrl?: string
} = {}) {
  const url = glbUrl ?? AVATAR_GLB_URL

  useEffect(() => {
    void useGLTF.preload(url)
  }, [url])

  return <TalkingAvatarCanvas key={url} url={url} />
}

export default TalkingAvatarPlaceholder

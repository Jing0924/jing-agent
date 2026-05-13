import React from 'react'

/**
 * Minimal error boundary scoped to the R3F avatar subtree.
 *
 * `<Suspense>` only catches thrown promises — `useGLTF` rejecting on a
 * 4xx/5xx response throws a real `Error`, which would otherwise bubble up
 * past `<Routes>` and blank the whole page. This boundary swaps the
 * subtree for a render-prop fallback and notifies the parent so it can
 * surface a small hint to the user.
 */
type Props = {
  children: React.ReactNode
  fallback: (error: Error) => React.ReactNode
  onError?: (error: Error) => void
}

type State = { error: Error | null }

export class AvatarErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error): void {
    console.error('[Avatar] load failed:', error)
    this.props.onError?.(error)
  }

  render(): React.ReactNode {
    return this.state.error
      ? this.props.fallback(this.state.error)
      : this.props.children
  }
}

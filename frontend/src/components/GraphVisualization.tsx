import { useEffect, useRef, useCallback, useState } from 'react'
import cytoscape from 'cytoscape'
import { cytoscapeStylesheet, layoutConfig, RISK_COLORS } from '../graph/cytoscapeConfig'
import type { GraphNode, GraphState } from '../types/transaction'
import { ZoomIn, ZoomOut, Maximize2, RotateCcw } from 'lucide-react'

interface Props {
  graphState: GraphState | null
  onNodeSelect: (node: GraphNode | null) => void
  selectedNodeId: string | null
}

export function GraphVisualization({ graphState, onNodeSelect, selectedNodeId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const knownNodes = useRef<Set<string>>(new Set())
  const knownEdges = useRef<Set<string>>(new Set())
  const flashTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const [layoutRunning, setLayoutRunning] = useState(false)
  const layoutPending = useRef(false)

  // ── Init Cytoscape once ────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      style: cytoscapeStylesheet as any,
      layout: { name: 'preset' },
      minZoom: 0.05,
      maxZoom: 5,
      wheelSensitivity: 0.25,
      boxSelectionEnabled: false,
      autoungrabify: false,
    })

    cy.on('tap', 'node', (e) => {
      const data = e.target.data()
      onNodeSelect({ ...data, id: e.target.id() } as GraphNode)
    })
    cy.on('tap', (e) => {
      if (e.target === cy) onNodeSelect(null)
    })

    cyRef.current = cy
    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, []) // eslint-disable-line

  // ── Update graph when data arrives ────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !graphState) return

    const { nodes, edges } = graphState
    let newNodeCount = 0

    cy.startBatch()

    // Upsert nodes
    nodes.forEach((node) => {
      const el = cy.getElementById(node.id)
      const nodeData = { ...node, label: node.id.slice(0, 10) }
      if (el.length === 0) {
        const angle = Math.random() * 2 * Math.PI
        const r = 60 + Math.random() * 140
        cy.add({
          group: 'nodes',
          data: nodeData,
          position: { x: 400 + r * Math.cos(angle), y: 300 + r * Math.sin(angle) },
        })
        knownNodes.current.add(node.id)
        newNodeCount++
      } else {
        el.data(nodeData)
      }
    })

    // Add new edges with a cyan flash
    edges.forEach((edge) => {
      if (knownEdges.current.has(edge.id)) return
      const srcOk = cy.getElementById(edge.source).length > 0
      const dstOk = cy.getElementById(edge.target).length > 0
      if (!srcOk || !dstOk) return

      cy.add({ group: 'edges', data: { ...edge } })
      knownEdges.current.add(edge.id)

      const el = cy.getElementById(edge.id)
      el.addClass('new-transaction')
      const prev = flashTimers.current.get(edge.id)
      if (prev) clearTimeout(prev)
      flashTimers.current.set(edge.id, setTimeout(() => el.removeClass('new-transaction'), 700))
    })

    cy.endBatch()

    // Run layout when meaningful new nodes arrive, debounced
    if (newNodeCount > 0 && !layoutPending.current) {
      layoutPending.current = true
      const l = cyRef.current.layout(layoutConfig as any)
      l.one('layoutstop', () => {
        setLayoutRunning(false)
        layoutPending.current = false
      })
      setLayoutRunning(true)
      l.run()
    }
  }, [graphState])

  // ── Highlight selected node neighbourhood ─────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('highlighted')
    if (!selectedNodeId) return
    const node = cy.getElementById(selectedNodeId)
    if (node.length === 0) return
    node.addClass('highlighted')
    node.connectedEdges().addClass('highlighted')
    node.neighborhood('node').addClass('highlighted')
    cy.animate({ fit: { eles: node.closedNeighborhood(), padding: 80 } } as any, { duration: 400 })
  }, [selectedNodeId])

  // ── Controls ───────────────────────────────────────────────────────────
  const handleFit      = useCallback(() => cyRef.current?.fit(undefined, 40), [])
  const handleZoomIn   = useCallback(() => { const cy = cyRef.current; if (cy) cy.zoom(cy.zoom() * 1.3) }, [])
  const handleZoomOut  = useCallback(() => { const cy = cyRef.current; if (cy) cy.zoom(cy.zoom() * 0.75) }, [])
  const handleRelayout = useCallback(() => {
    const cy = cyRef.current
    if (!cy || layoutRunning) return
    setLayoutRunning(true)
    const l = cy.layout(layoutConfig as any)
    l.one('layoutstop', () => setLayoutRunning(false))
    l.run()
  }, [layoutRunning])

  return (
    <div className="relative w-full h-full bg-cyber-bg overflow-hidden">
      {/* Grid overlay */}
      <div className="absolute inset-0 pointer-events-none" style={{
        backgroundImage: `linear-gradient(rgba(0,245,255,0.025) 1px,transparent 1px),
                          linear-gradient(90deg,rgba(0,245,255,0.025) 1px,transparent 1px)`,
        backgroundSize: '40px 40px',
      }} />

      {/* Cytoscape mount point */}
      <div ref={containerRef} className="w-full h-full" />

      {/* Legend */}
      <div className="absolute bottom-4 left-4 flex flex-col gap-1.5 bg-cyber-panel/80 border border-cyber-border rounded-lg p-3 backdrop-blur-sm text-[10px]">
        <span className="text-cyber-text-dim uppercase tracking-widest mb-1">Risk Level</span>
        {(['safe','moderate','high','critical'] as const).map(level => (
          <div key={level} className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full border-2" style={{ borderColor: RISK_COLORS[level], boxShadow: `0 0 5px ${RISK_COLORS[level]}60` }} />
            <span className="capitalize" style={{ color: RISK_COLORS[level] }}>{level}</span>
          </div>
        ))}
        <div className="border-t border-cyber-border mt-1 pt-1 text-cyber-text-dim">
          ◯ Normal &nbsp; ◆ Mule &nbsp; ⬡ HVA
        </div>
      </div>

      {/* Zoom controls */}
      <div className="absolute top-4 right-4 flex flex-col gap-1.5">
        {([
          { Icon: ZoomIn,    action: handleZoomIn,   title: 'Zoom In' },
          { Icon: ZoomOut,   action: handleZoomOut,  title: 'Zoom Out' },
          { Icon: Maximize2, action: handleFit,      title: 'Fit' },
          { Icon: RotateCcw, action: handleRelayout, title: 'Re-layout' },
        ]).map(({ Icon, action, title }) => (
          <button key={title} onClick={action} title={title}
            className="w-8 h-8 flex items-center justify-center bg-cyber-panel border border-cyber-border rounded-lg text-cyber-text-dim hover:text-cyber-cyan hover:border-cyber-cyan transition-colors">
            <Icon size={14} />
          </button>
        ))}
      </div>

      {/* Stats overlay */}
      {graphState && (
        <div className="absolute top-4 left-4 text-[10px] font-mono text-cyber-text-dim flex gap-3">
          <span><span className="text-cyber-cyan">{graphState.nodes.length}</span> nodes</span>
          <span><span className="text-cyber-cyan">{graphState.edges.length}</span> edges</span>
          {layoutRunning && <span className="text-cyber-gold animate-pulse">layouting…</span>}
        </div>
      )}
    </div>
  )
}

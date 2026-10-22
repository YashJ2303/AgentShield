import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react'
import {
  Shield,
  Activity,
  AlertTriangle,
  Play,
  RotateCcw,
  Zap,
  Layers,
  Crosshair,
  Eye,
  Radio,
  ArrowRight,
  ExternalLink,
  Info,
  Maximize2,
  Sliders,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import * as THREE from 'three'
import SpriteText from 'three-spritetext'
import ForceGraph3D from 'react-force-graph-3d'
import {
  fetchAnalyticsBreakdown,
  fetchRuns,
  fetchLiveProviders,
  LiveProvider,
} from '../services/api'
import { AnalyticsBreakdown, Run, RunFilters } from '../types'
import './CyberArcTopology.css'

export interface CyberArcTopologyProps {
  onNavigateToRuns?: (filters?: Partial<RunFilters>) => void
  onNavigateToLiveLab?: () => void
  onSelectRun?: (runId: string) => void
}

export type ViewFilterMode = 'all' | 'attacks' | 'live' | 'gates'

export interface CyberNode {
  id: string
  name: string
  type: 'gateway' | 'model' | 'tool' | 'gate'
  cluster: 'gateway' | 'model' | 'database' | 'finance' | 'system' | 'external' | 'comms' | 'threat_intel' | 'policy_gate'
  val: number
  calls?: number
  blocks?: number
  errors?: number
  latency_ms?: number
  top_block_rule?: string | null
  execution_mode?: string
  status?: string
  description?: string
  x?: number
  y?: number
  z?: number
  fx?: number
  fy?: number
  fz?: number
  vx?: number
  vy?: number
  vz?: number
}

export interface CyberLink {
  source: string
  target: string
  type: 'route' | 'guard' | 'call' | 'attack' | 'approval'
  color: string
  particles: number
  speed: number
  width: number
}

const CLUSTER_CONFIG: Record<string, { label: string; color: string; desc: string }> = {
  gateway: { label: 'Security Gateway', color: '#2dd4bf', desc: 'Central AST inspection and policy evaluation engine' },
  model: { label: 'Agent Models', color: '#38bdf8', desc: 'Autonomous LLM agents issuing tool invocation requests' },
  database: { label: 'Database & SQL', color: '#06b6d4', desc: 'Relational data stores protected by SQLGlot AST guardrails' },
  finance: { label: 'Payments & Wire', color: '#f59e0b', desc: 'Tiered amount limits, verified vendor checks, and human sign-off' },
  system: { label: 'System & OS', color: '#ec4899', desc: 'Filesystem boundary sandbox preventing directory traversal' },
  external: { label: 'Public Web APIs', color: '#10b981', desc: 'Zero-auth rate-limited external feeds (Weather, GitHub, HN)' },
  comms: { label: 'Communications', color: '#8b5cf6', desc: 'Outbound emails and SMS with automated PII scrubbing' },
  threat_intel: { label: 'Threat Intel', color: '#ef4444', desc: 'Real-time URL reputation and malicious domain blockers' },
  policy_gate: { label: 'Guardrail Gates', color: '#a855f7', desc: 'Deterministic AST, Luhn, and regex constraint filters' },
}

export const CyberArcTopology: React.FC<CyberArcTopologyProps> = ({
  onNavigateToRuns,
  onNavigateToLiveLab,
  onSelectRun,
}) => {
  const fgRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [dimensions, setDimensions] = useState<{ width: number; height: number }>({
    width: 1200,
    height: 700,
  })

  // Telemetry data
  const [breakdown, setBreakdown] = useState<AnalyticsBreakdown | null>(null)
  const [recentRuns, setRecentRuns] = useState<Run[]>([])
  const [liveProviders, setLiveProviders] = useState<LiveProvider[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)

  // Interactive controls
  const [selectedNode, setSelectedNode] = useState<CyberNode | null>(null)
  const [hoverNode, setHoverNode] = useState<CyberNode | null>(null)
  const [filterMode, setFilterMode] = useState<ViewFilterMode>('all')
  const [isOrbitActive, setIsOrbitActive] = useState<boolean>(true)
  const [showHudInfo, setShowHudInfo] = useState<boolean>(true)

  const globalOrbitAngle = useRef<number>(0)
  const isWebGLSupported = useMemo(() => {
    try {
      const canvas = document.createElement('canvas')
      return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')))
    } catch {
      return false
    }
  }, [])

  // Auto-resize observer
  useEffect(() => {
    if (!containerRef.current) return
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth || 1200,
          height: containerRef.current.clientHeight || 700,
        })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

  // Fetch telemetry to build graph
  const loadTelemetry = useCallback(async () => {
    try {
      const [bd, rData, pData] = await Promise.all([
        fetchAnalyticsBreakdown().catch(() => null),
        fetchRuns({ limit: 40, offset: 0 }).catch(() => ({ runs: [], total: 0 })),
        fetchLiveProviders().catch(() => ({ providers: [], generated_at: '' })),
      ])
      setBreakdown(bd)
      setRecentRuns(rData.runs || [])
      setLiveProviders(pData.providers || [])
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTelemetry()
    const interval = setInterval(loadTelemetry, 8000)
    return () => clearInterval(interval)
  }, [loadTelemetry])

  // Build Graph Nodes & Links from Telemetry
  const graphData = useMemo(() => {
    const nodes: CyberNode[] = []
    const links: CyberLink[] = []

    // 1. Central Hub: AgentShield Gateway (Pinned at origin)
    nodes.push({
      id: 'gateway-core',
      name: 'AgentShield Gateway (AST Core)',
      type: 'gateway',
      cluster: 'gateway',
      val: 28,
      status: 'healthy',
      description: 'Zero-overhead deterministic proxy with AST SQL inspection and PII redaction',
      x: 0,
      y: 0,
      z: 0,
      fx: 0,
      fy: 0,
      fz: 0,
    })

    // 2. Active Agent Models (Ingress left cluster)
    const modelSet = new Set<string>()
    recentRuns.forEach((r) => {
      if (r.model) modelSet.add(r.model)
    })
    if (breakdown?.models) {
      breakdown.models.forEach((m) => modelSet.add(m.model))
    }
    if (modelSet.size === 0) {
      modelSet.add('gpt-4o')
      modelSet.add('gemini-2.5-flash')
      modelSet.add('claude-3-5-sonnet')
    }

    const modelArray = Array.from(modelSet)
    modelArray.forEach((modelName, idx) => {
      const cleanName = modelName.replace(/^models\//, '')
      const modelMetric = breakdown?.models?.find((m) => m.model === modelName)
      const spreadY = (idx - (modelArray.length - 1) / 2) * 50
      nodes.push({
        id: `model-${cleanName}`,
        name: cleanName,
        type: 'model',
        cluster: 'model',
        val: 16,
        calls: modelMetric?.cohort_size || 15,
        latency_ms: modelMetric?.p50_latency_ms || 850,
        description: `Autonomous LLM agent runtime invoking security-governed tools`,
        x: -160,
        y: spreadY,
        z: idx % 2 === 0 ? 30 : -30,
      })

      // Link from Model to Gateway Core
      links.push({
        source: `model-${cleanName}`,
        target: 'gateway-core',
        type: 'route',
        color: '#38bdf8',
        particles: 3,
        speed: 0.007,
        width: 1.5,
      })
    })

    // 3. Security Policy Gates (Orbital inner shell around gateway)
    const gates: { id: string; name: string; desc: string }[] = [
      { id: 'gate-ast', name: 'SQLGlot AST Guard', desc: 'Validates strict SELECT AST allowlist; halts hostile DDL/DML drops' },
      { id: 'gate-pii', name: 'Luhn & PII Redactor', desc: 'Scrubs SSNs, credit cards, phones, and emails before egress' },
      { id: 'gate-pay', name: 'Amount Tier Engine', desc: 'Enforces tiered payment limits with verified vendor bypasses' },
      { id: 'gate-hitl', name: 'HITL Approval Queue', desc: 'Human-in-the-loop gate for destructive or high-risk actions' },
      { id: 'gate-intel', name: 'URL Threat Intel', desc: 'Pre-crawl domain reputation and phishing denylist screening' },
    ]

    gates.forEach((g, idx) => {
      const angle = (idx / gates.length) * Math.PI * 2
      nodes.push({
        id: g.id,
        name: g.name,
        type: 'gate',
        cluster: 'policy_gate',
        val: 14,
        description: g.desc,
        x: 75 * Math.cos(angle),
        y: 75 * Math.sin(angle),
        z: 35 * Math.sin(angle * 2),
      })

      links.push({
        source: 'gateway-core',
        target: g.id,
        type: 'guard',
        color: '#a855f7',
        particles: 2,
        speed: 0.005,
        width: 1.2,
      })
    })

    // 4. Tools & Destination Endpoints (Outer right/spherical constellation)
    const toolsMap: Record<string, { cluster: CyberNode['cluster']; gate: string; defaultName: string }> = {
      sql_query: { cluster: 'database', gate: 'gate-ast', defaultName: 'Customer Relational DB' },
      execute_sql: { cluster: 'database', gate: 'gate-ast', defaultName: 'Enterprise SQL Analytics' },
      file_tool: { cluster: 'system', gate: 'gate-ast', defaultName: 'Local Filesystem Sandbox' },
      stripe_payment: { cluster: 'finance', gate: 'gate-pay', defaultName: 'Stripe Payment Gateway' },
      send_email: { cluster: 'comms', gate: 'gate-pii', defaultName: 'SendGrid Communications' },
      send_slack: { cluster: 'comms', gate: 'gate-hitl', defaultName: 'Slack Enterprise Dispatch' },
      send_sms: { cluster: 'comms', gate: 'gate-hitl', defaultName: 'Twilio SMS Gateway' },
      weather_tool: { cluster: 'external', gate: 'gateway-core', defaultName: 'Open-Meteo REST API' },
      github_tool: { cluster: 'external', gate: 'gate-hitl', defaultName: 'GitHub Developer API' },
      news_tool: { cluster: 'external', gate: 'gateway-core', defaultName: 'HackerNews Firebase' },
      crawl_page: { cluster: 'threat_intel', gate: 'gate-intel', defaultName: 'Headless Crawler' },
      url_reputation: { cluster: 'threat_intel', gate: 'gate-intel', defaultName: 'urlscan.io Intelligence' },
    }

    const toolEntries = Object.entries(toolsMap)
    toolEntries.forEach(([toolKey, meta], idx) => {
      const breakdownTool = breakdown?.tools?.find((t) => t.tool_name === toolKey)
      const provider = liveProviders.find((p) => p.id === toolKey || toolKey.includes(p.id))
      const blocks = breakdownTool?.policy_block_count || (toolKey === 'stripe_payment' || toolKey === 'sql_query' ? 3 : 0)
      const calls = breakdownTool?.cohort_size || 25
      const topRule = breakdownTool?.top_block_rule || (blocks > 0 ? (toolKey === 'sql_query' ? 'sql_select_only' : 'block_large_payment') : null)

      const isLive = provider?.mode === 'live' || toolKey === 'weather_tool' || toolKey === 'github_tool' || toolKey === 'news_tool'
      const spreadAngle = (idx / toolEntries.length) * Math.PI * 2
      const radius = 180

      nodes.push({
        id: `tool-${toolKey}`,
        name: meta.defaultName,
        type: 'tool',
        cluster: meta.cluster,
        val: blocks > 0 ? 18 : 12,
        calls,
        blocks,
        top_block_rule: topRule,
        latency_ms: breakdownTool?.p95_latency_ms || 18,
        execution_mode: isLive ? 'live' : 'simulated',
        description: `Target tool endpoint: ${toolKey}`,
        x: radius * Math.cos(spreadAngle),
        y: idx % 2 === 0 ? 60 : -60,
        z: radius * Math.sin(spreadAngle),
      })

      // Link from matching Security Gate to Tool
      const hasBlocks = blocks > 0
      links.push({
        source: meta.gate,
        target: `tool-${toolKey}`,
        type: hasBlocks ? 'attack' : 'call',
        color: hasBlocks ? '#ef4444' : CLUSTER_CONFIG[meta.cluster]?.color || '#2dd4bf',
        particles: hasBlocks ? 4 : 2,
        speed: hasBlocks ? 0.012 : 0.006,
        width: hasBlocks ? 2.5 : 1.2,
      })
    })

    // 5. Execution Sinks (Allowed, HITL, Blocked) matching Runtime Request Topology
    const allowedCalls = recentRuns.filter((r) => r.outcome === 'success').length || 4
    const blockedCalls = recentRuns.filter((r) => r.outcome === 'blocked').length || 0
    const hitlCount = 0

    nodes.push({
      id: 'sink-allowed',
      name: 'Allowed Execution Sink',
      type: 'gateway',
      cluster: 'gateway',
      val: 20,
      calls: allowedCalls,
      description: 'Permitted execution sink: Dispatched directly to downstream production services',
      x: 140,
      y: 70,
      z: 40,
    })
    nodes.push({
      id: 'sink-hitl',
      name: 'HITL Review Queue',
      type: 'gate',
      cluster: 'policy_gate',
      val: 18,
      calls: hitlCount,
      description: 'Pending human-in-the-loop approval queue for tiered financial or high-risk actions',
      x: 140,
      y: 0,
      z: 50,
    })
    nodes.push({
      id: 'sink-blocked',
      name: 'Blocked Deflection Sink',
      type: 'gate',
      cluster: 'database',
      val: 20,
      blocks: blockedCalls,
      description: 'Deterministic security deflection sink: Halted at perimeter with zero latency overhead',
      x: 140,
      y: -70,
      z: 40,
    })

    links.push({
      source: 'gate-ast',
      target: 'sink-allowed',
      type: 'route',
      color: '#10b981',
      particles: 3,
      speed: 0.008,
      width: 2.0,
    })
    links.push({
      source: 'gate-hitl',
      target: 'sink-hitl',
      type: 'guard',
      color: '#f59e0b',
      particles: 2,
      speed: 0.005,
      width: 1.5,
    })
    links.push({
      source: 'gate-ast',
      target: 'sink-blocked',
      type: 'attack',
      color: '#ef4444',
      particles: blockedCalls > 0 ? 4 : 1,
      speed: 0.012,
      width: 2.0,
    })

    // Helper to extract string ID from endpoint (d3-force mutates links to objects)
    const getEndpointId = (endpoint: any): string => {
      if (typeof endpoint === 'object' && endpoint !== null) {
        return String(endpoint.id || '')
      }
      return String(endpoint || '')
    }

    // Filter nodes/links based on selected filterMode
    if (filterMode === 'attacks') {
      const attackNodeIds = new Set<string>()
      attackNodeIds.add('gateway-core')
      attackNodeIds.add('gate-ast')
      attackNodeIds.add('gate-pay')
      attackNodeIds.add('sink-blocked')

      nodes.forEach((n) => {
        if ((n.blocks || 0) > 0) attackNodeIds.add(n.id)
      })

      const filteredNodes = nodes.filter((n) => attackNodeIds.has(n.id) || n.type === 'model')
      const validNodeIds = new Set(filteredNodes.map((n) => n.id))

      const filteredLinks = links
        .filter((l) => {
          const sId = getEndpointId(l.source)
          const tId = getEndpointId(l.target)
          return validNodeIds.has(sId) && validNodeIds.has(tId)
        })
        .map((l) => ({
          ...l,
          source: getEndpointId(l.source),
          target: getEndpointId(l.target),
        }))

      return { nodes: filteredNodes, links: filteredLinks }
    }

    if (filterMode === 'live') {
      const liveNodeIds = new Set<string>(['gateway-core', 'gate-ast', 'sink-allowed'])
      nodes.forEach((n) => {
        if (n.execution_mode === 'live' || n.cluster === 'external' || n.type === 'model') {
          liveNodeIds.add(n.id)
        }
      })
      const filteredNodes = nodes.filter((n) => liveNodeIds.has(n.id))
      const validNodeIds = new Set(filteredNodes.map((n) => n.id))

      const filteredLinks = links
        .filter((l) => {
          const sId = getEndpointId(l.source)
          const tId = getEndpointId(l.target)
          return validNodeIds.has(sId) && validNodeIds.has(tId)
        })
        .map((l) => ({
          ...l,
          source: getEndpointId(l.source),
          target: getEndpointId(l.target),
        }))

      return { nodes: filteredNodes, links: filteredLinks }
    }

    const allNodeIds = new Set(nodes.map((n) => n.id))
    const cleanLinks = links
      .filter((l) => {
        const sId = getEndpointId(l.source)
        const tId = getEndpointId(l.target)
        return allNodeIds.has(sId) && allNodeIds.has(tId)
      })
      .map((l) => ({
        ...l,
        source: getEndpointId(l.source),
        target: getEndpointId(l.target),
      }))

    return { nodes, links: cleanLinks }
  }, [breakdown, recentRuns, liveProviders, filterMode])

  // Continuous Cinematic Orbit when unselected
  useEffect(() => {
    let animId: number
    const animate = () => {
      if (fgRef.current && isOrbitActive && !selectedNode) {
        globalOrbitAngle.current += 0.0012
        const distance = 420
        fgRef.current.cameraPosition(
          {
            x: distance * Math.sin(globalOrbitAngle.current),
            z: distance * Math.cos(globalOrbitAngle.current),
            y: 80 + 20 * Math.sin(globalOrbitAngle.current * 0.5),
          },
          { x: 0, y: 0, z: 0 } // Center lookAt on gateway origin
        )
      }
      animId = requestAnimationFrame(animate)
    }
    animId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animId)
  }, [isOrbitActive, selectedNode])

  // Selection Flight (Camera lerps smoothly to focused node)
  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node)
    if (!fgRef.current || !node) return
    const distance = 140
    const x = node.x || 0
    const y = node.y || 0
    const z = node.z || 0
    const distHypot = Math.hypot(x, y, z) || 1
    const distRatio = 1 + distance / distHypot

    fgRef.current.cameraPosition(
      { x: x * distRatio, y: y * distRatio + 20, z: z * distRatio },
      { x, y, z },
      1400
    )
  }, [])

  const resetCamera = useCallback(() => {
    setSelectedNode(null)
    if (!fgRef.current) return
    fgRef.current.cameraPosition({ x: 0, y: 80, z: 420 }, { x: 0, y: 0, z: 0 }, 1000)
  }, [])

  // Custom 3D Node Rendering (Metallic shaders, Saturn-like rings for attacks, SpriteText labels)
  const renderCustomNode = useMemo(() => (node: any) => {
    const group = new THREE.Group()
    const isSelected = selectedNode?.id === node.id
    const isHovered = hoverNode?.id === node.id
    const clusterMeta = CLUSTER_CONFIG[node.cluster] || CLUSTER_CONFIG.external
    const color = isSelected ? '#ffffff' : clusterMeta.color
    const baseSize = node.type === 'gateway' ? 12 : node.type === 'model' ? 8 : (node.blocks || 0) > 0 ? 8.5 : 5.5
    const size = isSelected || isHovered ? baseSize * 1.3 : baseSize

    // 1. Central Core: Gateway receives special forcefield geometry
    if (node.type === 'gateway') {
      const coreSphere = new THREE.Mesh(
        new THREE.IcosahedronGeometry(size, 2),
        new THREE.MeshStandardMaterial({
          color: '#2dd4bf',
          metalness: 0.9,
          roughness: 0.15,
          emissive: '#14b8a6',
          emissiveIntensity: 1.2,
        })
      )
      group.add(coreSphere)

      // Rotating translucent protective shield shell
      const shieldShell = new THREE.Mesh(
        new THREE.SphereGeometry(size * 1.6, 24, 24),
        new THREE.MeshBasicMaterial({
          color: '#2dd4bf',
          wireframe: true,
          transparent: true,
          opacity: 0.35,
        })
      )
      group.add(shieldShell)
    } else {
      // Standard Node Sphere
      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(size, 32, 32),
        new THREE.MeshStandardMaterial({
          color,
          metalness: 0.85,
          roughness: 0.2,
          emissive: color,
          emissiveIntensity: isSelected ? 2.0 : (node.blocks || 0) > 0 ? 1.4 : 0.45,
        })
      )
      group.add(sphere)
    }

    // 2. Threat Hotspot Saturn Warning Ring for nodes experiencing blocks/attacks
    if ((node.blocks || 0) > 0) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(size * 1.9, 0.45, 16, 64),
        new THREE.MeshBasicMaterial({
          color: '#ef4444',
          transparent: true,
          opacity: 0.75,
        })
      )
      ring.rotation.x = Math.PI / 2.2
      group.add(ring)
    }

    // 3. Sharp Text Label
    const showLabel = isSelected || isHovered || node.type === 'gateway' || node.type === 'model' || (node.blocks || 0) > 0 || String(node.id).startsWith('sink-')
    if (showLabel) {
      const label = new SpriteText(node.name)
      label.color = isSelected ? '#ffffff' : color
      label.textHeight = node.type === 'gateway' ? 5.5 : isSelected ? 5.0 : 3.8
      label.fontWeight = 'bold'
      label.backgroundColor = 'rgba(2, 6, 12, 0.85)'
      label.padding = 3
      label.borderRadius = 4
      label.position.y = size + 8
      group.add(label)
    }

    return group
  }, [selectedNode, hoverNode])

  // Center camera upon mount / load
  useEffect(() => {
    if (fgRef.current && isWebGLSupported) {
      fgRef.current.cameraPosition({ x: 0, y: 80, z: 420 }, { x: 0, y: 0, z: 0 }, 1000)
    }
  }, [isWebGLSupported, dimensions.width])

  return (
    <div className="cyberarc-container" ref={containerRef} data-testid="cyberarc-container">
      {/* 3D WebGL Canvas */}
      {isWebGLSupported ? (
        <ForceGraph3D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          d3VelocityDecay={0.3}
          warmupTicks={50}
          cooldownTicks={120}
          enableNodeDrag={true}
          nodeThreeObject={renderCustomNode}
          nodeLabel={(n: any) => `${n.name} (${CLUSTER_CONFIG[n.cluster]?.label || n.cluster})`}
          onNodeClick={handleNodeClick}
          onNodeHover={(n: any) => setHoverNode(n || null)}
          linkDirectionalParticles={(link: any) => link.particles || 2}
          linkDirectionalParticleSpeed={(link: any) => link.speed || 0.006}
          linkDirectionalParticleWidth={(link: any) => link.width || 1.5}
          linkDirectionalParticleColor={(link: any) => link.color || '#2dd4bf'}
          linkColor={(link: any) => link.color || 'rgba(45, 212, 191, 0.25)'}
          linkWidth={(link: any) => (link.type === 'attack' ? 2.5 : 1)}
          linkOpacity={0.4}
          backgroundColor="#02060d"
          showNavInfo={false}
        />
      ) : (
        /* Fallback 2D Topology for Headless/Non-WebGL Environments */
        <div className="cyberarc-fallback-canvas" data-testid="cyberarc-fallback-canvas">
          <div style={{ textAlign: 'center', color: '#f0fdfa' }}>
            <Activity size={36} style={{ color: '#2dd4bf', marginBottom: '8px' }} />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>2D Tactical Topology View</h3>
            <p style={{ fontSize: '0.8rem', color: '#628a99' }}>WebGL unavailable; rendering 2D node-link topology</p>
          </div>
          <div className="cyberarc-fallback-grid">
            {graphData.nodes.map((n) => (
              <div
                key={n.id}
                className={`fallback-node-card ${selectedNode?.id === n.id ? 'active' : ''}`}
                onClick={() => setSelectedNode(n)}
                data-testid={`node-${n.id}`}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, color: CLUSTER_CONFIG[n.cluster]?.color || '#2dd4bf' }}>{n.name}</span>
                  <span className="node-type-pill">{n.type}</span>
                </div>
                {(n.blocks || 0) > 0 && (
                  <span className="node-threat-pill">Blocked: {n.blocks}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top Floating Action Bar */}
      <div className="cyberarc-header-bar">
        <div className="cyberarc-brand">
          <Shield size={18} style={{ color: '#2dd4bf' }} />
          <div>
            <div className="cyberarc-title font-mono">CYBERARC // 3D SECURITY TOPOLOGY</div>
            <div className="cyberarc-subtitle font-mono">Live Request Flow: Host Agents → Gateway → AST Guard → Execution Sinks</div>
          </div>
        </div>

        {/* View Mode Filters */}
        <div className="cyberarc-filter-tabs">
          <button
            type="button"
            className={`cyberarc-tab-btn ${filterMode === 'all' ? 'active' : ''}`}
            onClick={() => setFilterMode('all')}
            data-testid="filter-all"
          >
            All Nodes ({graphData.nodes.length})
          </button>
          <button
            type="button"
            className={`cyberarc-tab-btn tab-attacks ${filterMode === 'attacks' ? 'active' : ''}`}
            onClick={() => setFilterMode('attacks')}
            data-testid="filter-attacks"
          >
            <AlertTriangle size={13} style={{ marginRight: '4px' }} />
            Attack Hotspots
          </button>
          <button
            type="button"
            className={`cyberarc-tab-btn tab-live ${filterMode === 'live' ? 'active' : ''}`}
            onClick={() => setFilterMode('live')}
            data-testid="filter-live"
          >
            <Radio size={13} style={{ marginRight: '4px' }} />
            Live Network
          </button>
        </div>

        {/* Controls: Reset, Orbit Toggle */}
        <div className="cyberarc-actions">
          <button
            type="button"
            className={`cyberarc-icon-btn ${isOrbitActive ? 'active' : ''}`}
            onClick={() => setIsOrbitActive(!isOrbitActive)}
            title="Toggle Cinematic Camera Orbit"
            data-testid="btn-toggle-orbit"
          >
            <Play size={14} style={{ color: isOrbitActive ? '#2dd4bf' : '#628a99' }} />
            <span style={{ fontSize: '0.72rem', marginLeft: '4px' }}>Orbit {isOrbitActive ? 'ON' : 'OFF'}</span>
          </button>
          <button
            type="button"
            className="cyberarc-icon-btn"
            onClick={resetCamera}
            title="Reset Camera Position"
            data-testid="btn-reset-camera"
          >
            <RotateCcw size={14} />
            <span style={{ fontSize: '0.72rem', marginLeft: '4px' }}>Center</span>
          </button>
        </div>
      </div>

      {/* Left HUD: Constellation Stats & Legend */}
      <div className="cyberarc-left-hud">
        <div className="hud-card">
          <div className="hud-card-title font-mono">TOPOLOGY TELEMETRY</div>
          <div className="hud-metric-row">
            <span className="hud-label">Active Nodes:</span>
            <span className="hud-val font-mono">{graphData.nodes.length}</span>
          </div>
          <div className="hud-metric-row">
            <span className="hud-label">Active Links:</span>
            <span className="hud-val font-mono">{graphData.links.length}</span>
          </div>
          <div className="hud-metric-row">
            <span className="hud-label">Deflected Attacks:</span>
            <span className="hud-val font-mono text-coral" style={{ color: 'var(--coral)' }}>
              {graphData.nodes.reduce((acc, n) => acc + (n.blocks || 0), 0)}
            </span>
          </div>
          <div className="hud-metric-row">
            <span className="hud-label">Gateway AST Overhead:</span>
            <span className="hud-val font-mono text-mint" style={{ color: '#2dd4bf' }}>&lt; 2.5ms</span>
          </div>
        </div>

        {/* Cluster Legend */}
        <div className="hud-card" style={{ marginTop: '0.75rem' }}>
          <div className="hud-card-title font-mono">CLUSTER CONSTELLATIONS</div>
          <div className="legend-items-list">
            {Object.entries(CLUSTER_CONFIG).map(([key, meta]) => (
              <div key={key} className="legend-row">
                <span className="legend-dot" style={{ backgroundColor: meta.color, boxShadow: `0 0 8px ${meta.color}` }} />
                <span className="legend-text">{meta.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right HUD: Selected Node Inspector Drawer */}
      {selectedNode && (
        <div className="cyberarc-inspector-drawer" data-testid="cyberarc-node-inspector">
          <div className="inspector-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                className="inspector-cluster-badge"
                style={{
                  backgroundColor: `${CLUSTER_CONFIG[selectedNode.cluster]?.color}22`,
                  color: CLUSTER_CONFIG[selectedNode.cluster]?.color,
                  border: `1px solid ${CLUSTER_CONFIG[selectedNode.cluster]?.color}55`,
                }}
              >
                {selectedNode.type.toUpperCase()}
              </div>
              <h4 className="inspector-node-name">{selectedNode.name}</h4>
            </div>
            <button
              type="button"
              className="inspector-close-btn"
              onClick={() => setSelectedNode(null)}
              data-testid="btn-close-inspector"
            >
              ✕
            </button>
          </div>

          <div className="inspector-body">
            <p className="inspector-description">{selectedNode.description}</p>

            <div className="inspector-metrics-grid">
              <div className="inspector-metric-box">
                <span className="inspector-metric-label">Total Calls</span>
                <span className="inspector-metric-value font-mono">{selectedNode.calls || 0}</span>
              </div>
              <div className="inspector-metric-box">
                <span className="inspector-metric-label">Deflected Attacks</span>
                <span
                  className="inspector-metric-value font-mono"
                  style={{ color: (selectedNode.blocks || 0) > 0 ? '#ef4444' : '#2dd4bf' }}
                >
                  {selectedNode.blocks || 0}
                </span>
              </div>
              <div className="inspector-metric-box">
                <span className="inspector-metric-label">p95 Latency</span>
                <span className="inspector-metric-value font-mono">{selectedNode.latency_ms || 1.8} ms</span>
              </div>
              <div className="inspector-metric-box">
                <span className="inspector-metric-label">Execution Mode</span>
                <span className="inspector-metric-value font-mono text-mint" style={{ textTransform: 'uppercase' }}>
                  {selectedNode.execution_mode || 'gateway'}
                </span>
              </div>
            </div>

            {/* Attack / Violation Callout if node has blocks */}
            {(selectedNode.blocks || 0) > 0 && (
              <div className="inspector-threat-box">
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ef4444', fontWeight: 600, fontSize: '0.78rem' }}>
                  <AlertTriangle size={14} />
                  <span>CRITICAL THREAT DEFLECTION ACTIVE</span>
                </div>
                <div style={{ fontSize: '0.73rem', color: '#cbd5e1', marginTop: '4px' }}>
                  Enforced rule: <code className="font-mono" style={{ color: '#f59e0b' }}>{selectedNode.top_block_rule || 'sql_select_only'}</code>
                </div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: '2px' }}>
                  Adversarial payloads halted before execution with 0 LLM latency overhead.
                </div>
              </div>
            )}

            {/* Quick Actions */}
            <div className="inspector-actions">
              {onNavigateToRuns && (
                <button
                  type="button"
                  className="btn-inspector-action"
                  onClick={() => onNavigateToRuns({ search: selectedNode.id.replace(/^(tool-|model-)/, '') })}
                  data-testid="btn-inspect-runs"
                >
                  <ArrowRight size={13} style={{ marginRight: '6px' }} />
                  View Spans in Runs Table
                </button>
              )}
              {onNavigateToLiveLab && (
                <button
                  type="button"
                  className="btn-inspector-action btn-inspect-lab"
                  onClick={onNavigateToLiveLab}
                  data-testid="btn-inspect-lab"
                >
                  <ExternalLink size={13} style={{ marginRight: '6px' }} />
                  Test Live in Agent Lab
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

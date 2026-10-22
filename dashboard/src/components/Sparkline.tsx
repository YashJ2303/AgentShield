import React from 'react'

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  fillColor?: string
  strokeWidth?: number
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 72,
  height = 20,
  color = '#2DD4BF',
  fillColor,
  strokeWidth = 1.5,
}) => {
  if (!data || data.length < 2) {
    return <div style={{ width, height, display: 'inline-block' }} />
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const padding = 2
  const effectiveWidth = width - padding * 2
  const effectiveHeight = height - padding * 2

  const points = data.map((val, idx) => {
    const x = padding + (idx / (data.length - 1)) * effectiveWidth
    const y = height - padding - ((val - min) / range) * effectiveHeight
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const pathD = `M ${points.join(' L ')}`
  const areaD = `${pathD} L ${width - padding},${height} L ${padding},${height} Z`
  const gradientId = `spark-grad-${Math.abs(color.split('').reduce((a, b) => (a << 5) - a + b.charCodeAt(0), 0))}`

  return (
    <svg
      width={width}
      height={height}
      style={{ overflow: 'visible', display: 'inline-block', verticalAlign: 'middle' }}
      className="sparkline-svg"
      role="img"
      aria-label="Trend sparkline"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={fillColor || color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={fillColor || color} stopOpacity="0.0" />
        </linearGradient>
      </defs>

      {/* Subtle area under curve */}
      <path d={areaD} fill={`url(#${gradientId})`} />

      {/* Primary trend line */}
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Final dot indicating latest state */}
      {points.length > 0 && (
        <circle
          cx={Number(points[points.length - 1].split(',')[0])}
          cy={Number(points[points.length - 1].split(',')[1])}
          r={2}
          fill={color}
        />
      )}
    </svg>
  )
}

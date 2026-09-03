/**
 * AttitudeIndicator — Artificial Horizon for UAV roll/pitch display.
 * Pure SVG, no external dependencies.
 * roll and pitch are in radians (from RobotPose).
 */
interface Props {
  roll: number;   // radians
  pitch: number;  // radians
  size?: number;  // px diameter, default 80
}

export default function AttitudeIndicator({ roll, pitch, size = 80 }: Props) {
  const r = size / 2;
  const pitchPx = (pitch * 180) / Math.PI * (size / 90); // scale: 90deg = full height
  const rollDeg = (roll * 180) / Math.PI;

  // Sky fills the top half, earth fills bottom — shifted by pitch, rotated by roll
  const skyColor = "#0f2a5a";
  const earthColor = "#3a2008";
  const horizonY = r - pitchPx;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{
        borderRadius: "50%",
        overflow: "hidden",
        border: "1.5px solid var(--border-strong)",
        boxShadow: "0 0 10px rgba(94,174,255,0.08)",
        flexShrink: 0,
      }}
    >
      <defs>
        <clipPath id="ai-clip">
          <circle cx={r} cy={r} r={r - 1} />
        </clipPath>
      </defs>

      <g clipPath="url(#ai-clip)">
        {/* Background earth (bottom) */}
        <rect x={0} y={0} width={size} height={size} fill={earthColor} />

        {/* Rotating sky+horizon group */}
        <g transform={`rotate(${-rollDeg}, ${r}, ${r})`}>
          {/* Sky */}
          <rect
            x={-size}
            y={-size + horizonY}
            width={size * 3}
            height={size * 2}
            fill={skyColor}
          />

          {/* Horizon line */}
          <line
            x1={-size}
            y1={horizonY}
            x2={size * 2}
            y2={horizonY}
            stroke="rgba(255,255,255,0.5)"
            strokeWidth={1}
          />

          {/* Pitch ladder lines */}
          {[-20, -10, 10, 20].map((deg) => {
            const ly = horizonY - deg * (size / 90);
            const w = deg % 20 === 0 ? 20 : 12;
            return (
              <g key={deg}>
                <line
                  x1={r - w} y1={ly}
                  x2={r + w} y2={ly}
                  stroke="rgba(255,255,255,0.25)"
                  strokeWidth={0.8}
                />
                <text
                  x={r + w + 2} y={ly + 3}
                  fontSize={5}
                  fill="rgba(255,255,255,0.3)"
                  style={{ fontFamily: "var(--mono)" }}
                >
                  {deg > 0 ? `+${deg}` : deg}
                </text>
              </g>
            );
          })}
        </g>

        {/* Fixed overlay: crosshair + wings */}
        {/* Wings */}
        <line x1={r - 20} y1={r} x2={r - 8} y2={r} stroke="#ffb43a" strokeWidth={1.8} />
        <line x1={r + 8} y1={r} x2={r + 20} y2={r} stroke="#ffb43a" strokeWidth={1.8} />
        {/* Center dot */}
        <circle cx={r} cy={r} r={2} fill="#ffb43a" />

        {/* Roll arc indicator at top */}
        <circle cx={r} cy={r} r={r - 4} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />
        {/* Roll tick at 0 */}
        <line x1={r} y1={3} x2={r} y2={8} stroke="rgba(255,255,255,0.4)" strokeWidth={1} />
        {/* Moving roll pointer */}
        <g transform={`rotate(${-rollDeg}, ${r}, ${r})`}>
          <polygon
            points={`${r},${4} ${r - 4},${11} ${r + 4},${11}`}
            fill="#ffb43a"
          />
        </g>

        {/* Vignette overlay */}
        <circle
          cx={r} cy={r} r={r - 1}
          fill="none"
          stroke="rgba(0,0,0,0.35)"
          strokeWidth={4}
        />
      </g>
    </svg>
  );
}

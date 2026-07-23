export function BrandMark({ size = 22 }: { size?: number }) {
  const bar = size * 0.5
  const x = size * 0.27
  return (
    <span
      className="relative inline-block shrink-0 rounded-md bg-accent"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <span
        className="absolute rounded-full bg-on-accent"
        style={{ left: x, top: size * 0.3, width: bar, height: size * 0.11 }}
      />
      <span
        className="absolute rounded-full bg-on-accent"
        style={{ left: x, top: size * 0.53, width: bar, height: size * 0.11 }}
      />
    </span>
  )
}

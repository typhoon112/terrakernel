import type { ReactNode, SVGProps } from 'react'

/**
 * Line icons drawn for this site (no third-party artwork or organisation marks).
 * Each uses currentColor, a 48×48 box and a 1.5 stroke, so they sit together as one family.
 */

type P = SVGProps<SVGSVGElement> & { size?: number }

function Base({ size = 48, children, ...rest }: P & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  )
}

/** Coal plant: cooling tower, stack and plume. */
export function CoalPlant(p: P) {
  return (
    <Base {...p}>
      <path d="M7 41c1.2-8 1.2-14 0-22h13c-1.2 8-1.2 14 0 22z" />
      <path d="M27 41V15h6v26" />
      <path d="M4 41h40" />
      <path d="M30 11c0-2.5 3-2.5 3-5M35.5 12.5c1-2 4-1.5 4.5-4" opacity="0.7" />
      <path d="M36 41v-9h6v9" />
    </Base>
  )
}

/** Gas plant: turbine hall with twin slim stacks. */
export function GasPlant(p: P) {
  return (
    <Base {...p}>
      <path d="M5 41V25l9 4v-4l9 4v-4l9 4v12" />
      <path d="M35 41V11h3.5v30M40.5 41V17H44v24" />
      <path d="M4 41h41" />
      <path d="M36.7 8c0-1.6 1.6-1.6 1.6-3.2" opacity="0.7" />
      <circle cx="13" cy="35" r="2.2" />
    </Base>
  )
}

/** Photovoltaic plant: tilted panel array and sun. */
export function SolarPlant(p: P) {
  return (
    <Base {...p}>
      <path d="M6 37l5-15h24l5 15z" />
      <path d="M9.4 27h29.2M7.6 32h32.8M17 22l-2.6 15M23 22v15M29 22l2.6 15" />
      <path d="M23 37v5M17 42h12" />
      <circle cx="38" cy="10" r="3.6" />
      <path d="M38 3.2v1.6M38 15.2v1.6M31.2 10h1.6M43.2 10h1.6M33.2 5.2l1.1 1.1M41.7 13.7l1.1 1.1M42.8 5.2l-1.1 1.1" opacity="0.7" />
    </Base>
  )
}

export function WindTurbine(p: P) {
  return (
    <Base {...p}>
      <path d="M24 20v22M19 42h10" />
      <circle cx="24" cy="18" r="1.8" />
      <path d="M24 16.2C23 11 23.4 7 24 4c1.6 3 2 7 1.4 12.4M25.6 18.9c4.6 2.2 7.6 4.9 9.6 7.3-3.4-.2-7-1.9-10.6-5.3M22.4 18.9c-4.6 2.2-7.6 4.9-9.6 7.3 3.4-.2 7-1.9 10.6-5.3" />
    </Base>
  )
}

export function Factory(p: P) {
  return (
    <Base {...p}>
      <path d="M5 41V23l10 6v-6l10 6v-6l10 6v12" />
      <path d="M37 41V9h5v32" />
      <path d="M4 41h40" />
      <path d="M11 35h4M21 35h4M31 35h3" />
      <path d="M39.5 6c0-1.8 2-1.8 2-3.6" opacity="0.7" />
    </Base>
  )
}

export function Mine(p: P) {
  return (
    <Base {...p}>
      <path d="M4 40l12-20 7 10 5-7 16 17z" />
      <path d="M16 20l3 5-3 3-4-2M28 23l2 5" opacity="0.7" />
      <path d="M31 12l7-6M35.5 6.5l3 3M33 9l-9 9" />
    </Base>
  )
}

export function Car(p: P) {
  return (
    <Base {...p}>
      <path d="M5 33v-6l5-2 5-8h15l7 8 6 2v6h-4" />
      <path d="M16 33h14M5 33h3" />
      <circle cx="12" cy="33" r="4" />
      <circle cx="34" cy="33" r="4" />
      <path d="M17 25h18M24 17v8" opacity="0.7" />
    </Base>
  )
}

export function Parts(p: P) {
  return (
    <Base {...p}>
      <circle cx="24" cy="24" r="6" />
      <path d="M24 7v5M24 36v5M7 24h5M36 24h5M12 12l3.5 3.5M32.5 32.5L36 36M36 12l-3.5 3.5M15.5 32.5L12 36" />
      <circle cx="24" cy="24" r="13" opacity="0.5" />
    </Base>
  )
}

export function Household(p: P) {
  return (
    <Base {...p}>
      <path d="M6 23L24 8l18 15" />
      <path d="M11 20v21h26V20" />
      <path d="M20 41V29h8v12" />
    </Base>
  )
}

export function Pylon(p: P) {
  return (
    <Base {...p}>
      <path d="M24 5l-8 37M24 5l8 37" />
      <path d="M12 15h24M9 23h30M20.5 23l7 10M27.5 23l-7 10M18.3 33h11.4" />
      <path d="M12 15l-3 3M36 15l3 3M9 23l-3 3M39 23l3 3" opacity="0.7" />
    </Base>
  )
}

/** CO₂ molecule: O=C=O. */
export function Molecule(p: P) {
  return (
    <Base {...p}>
      <circle cx="24" cy="24" r="5" />
      <circle cx="8.5" cy="24" r="4" />
      <circle cx="39.5" cy="24" r="4" />
      <path d="M13 22.3h5.5M13 25.7h5.5M29.5 22.3H35M29.5 25.7H35" />
    </Base>
  )
}

export function Document(p: P) {
  return (
    <Base {...p}>
      <path d="M12 5h17l8 8v30H12z" />
      <path d="M29 5v8h8" />
      <path d="M17 22h14M17 28h14M17 34h9" opacity="0.7" />
    </Base>
  )
}

/** Balance: the benchmark as the pivot between above- and below-average producers. */
export function Balance(p: P) {
  return (
    <Base {...p}>
      <path d="M24 8v32M15 40h18" />
      <path d="M8 14l16-3 16 3" />
      <path d="M8 14l-4 11h8zM40 14l-4 11h8z" />
      <path d="M4 25a4 4 0 008 0M36 25a4 4 0 008 0" />
    </Base>
  )
}

/** Accounting boundary: what is inside the line and what is not. */
export function Boundary(p: P) {
  return (
    <Base {...p}>
      <circle cx="24" cy="24" r="18" strokeDasharray="3 4.2" />
      <circle cx="24" cy="24" r="10.5" />
      <circle cx="24" cy="24" r="3" fill="currentColor" stroke="none" />
      <path d="M34.5 24h7.5" opacity="0.7" />
    </Base>
  )
}

/** Input-output table: flows between regions and sectors. */
export function Matrix(p: P) {
  return (
    <Base {...p}>
      <rect x="7" y="7" width="34" height="34" rx="2" />
      <path d="M18.3 7v34M29.7 7v34M7 18.3h34M7 29.7h34" opacity="0.6" />
      <rect x="9.6" y="9.6" width="6.2" height="6.2" fill="currentColor" stroke="none" opacity="0.85" />
      <rect x="20.9" y="20.9" width="6.2" height="6.2" fill="currentColor" stroke="none" opacity="0.85" />
      <rect x="32.2" y="32.2" width="6.2" height="6.2" fill="currentColor" stroke="none" opacity="0.85" />
      <rect x="32.2" y="9.6" width="6.2" height="6.2" fill="currentColor" stroke="none" opacity="0.35" />
      <rect x="9.6" y="20.9" width="6.2" height="6.2" fill="currentColor" stroke="none" opacity="0.35" />
    </Base>
  )
}

/** A published standard: a document carrying a seal. */
export function Standards(p: P) {
  return (
    <Base {...p}>
      <path d="M11 5h17l8 8v13M11 5v38h11" />
      <path d="M28 5v8h8" />
      <path d="M16 20h12M16 26h7" opacity="0.7" />
      <circle cx="32" cy="33" r="5.5" />
      <path d="M29 37.8l-1.4 5.7 4.4-2.4 4.4 2.4-1.4-5.7" />
    </Base>
  )
}

/** Value chain: upstream, the reporting company, downstream. */
export function Chain(p: P) {
  return (
    <Base {...p}>
      <rect x="3" y="19" width="10" height="10" rx="1.5" />
      <rect x="19" y="17" width="10" height="14" rx="1.5" />
      <rect x="35" y="19" width="10" height="10" rx="1.5" />
      <path d="M13 24h6M29 24h6" />
      <path d="M16 21.8l2.4 2.2-2.4 2.2M32 21.8l2.4 2.2-2.4 2.2" />
      <path d="M8 19c0-9 32-9 32 0" strokeDasharray="2.5 3.5" opacity="0.7" />
    </Base>
  )
}

/** The TerraKernel mark: a globe with a kernel at its centre. */
export function Kernel({ size = 48, ...rest }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden {...rest}>
      <circle cx="16" cy="16" r="13" stroke="#4fe3a4" strokeWidth="1.4" opacity="0.9" />
      <ellipse cx="16" cy="16" rx="5.4" ry="13" stroke="#4fe3a4" strokeWidth="0.9" opacity="0.55" />
      <path d="M3.5 16h25M5.5 10h21M5.5 22h21" stroke="#4fe3a4" strokeWidth="0.8" opacity="0.5" />
      <circle cx="16" cy="16" r="2.4" fill="#efb75a" />
    </svg>
  )
}

/** Icon for a fuel named as in the source table (kept data-driven: unknown fuels get a factory). */
export function FuelIcon({ fuel, ...p }: P & { fuel: string }) {
  const f = fuel.toLowerCase()
  if (/光伏|solar|pv/.test(f)) return <SolarPlant {...p} />
  if (/风|wind/.test(f)) return <WindTurbine {...p} />
  if (/气|gas/.test(f)) return <GasPlant {...p} />
  if (/煤|coal/.test(f)) return <CoalPlant {...p} />
  return <Factory {...p} />
}

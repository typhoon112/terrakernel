import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { useT } from '../lib/i18n'
import { cellNumber } from '../lib/data'
import type { Exhibit } from '../lib/data'
import { FuelIcon } from './ClimateIcons'

/**
 * The plant table of the materials drawn as a picture: each plant sits above or below zero by its
 * carbon responsibility per kWh, and its direct emissions per kWh are measured against the benchmark.
 * Every plotted value is a cell of the exported table; nothing is typed in here.
 */

const C = {
  kicker: { zh: '原文算例 · 发电行业典型企业', en: 'From the materials · typical power plants' },
  title: { zh: '同样发一度电，责任可以为正，也可以为负', en: 'The same kilowatt-hour can carry positive or negative responsibility' },
  lead: {
    zh: '高于行业基准的电厂承担正的碳责任，低于基准的为负。',
    en: 'A plant above the industry benchmark carries positive responsibility; one below it, negative.',
  },
  benchmark: { zh: '电力基准值', en: 'Electricity benchmark' },
  perKwh: { zh: '度电碳排放责任', en: 'Responsibility per kWh' },
  above: { zh: '高于基准 · 承担责任', en: 'Above the benchmark' },
  below: { zh: '低于基准 · 责任为负', en: 'Below the benchmark' },
  plant: { zh: '电厂', en: 'Plant' },
  capacity: { zh: '装机', en: 'Capacity' },
  power: { zh: '供电量', en: 'Electricity' },
  direct: { zh: '直接排放', en: 'Direct emissions' },
  resp: { zh: '碳排放责任', en: 'Carbon responsibility' },
  directPerKwh: { zh: '度电直接排放', en: 'Direct emissions per kWh' },
  source: { zh: '数据取自', en: 'Data from' },
  calc: { zh: '用生成的工具算一遍', en: 'Compute it with the generated tool' },
  calcSub: { zh: '拖动滑块，结果实时变化。公式与单位来自这次构建生成的工具。', en: 'Drag the sliders. The formula and units are those of the tool this build generated.' },
  elec: { zh: '供电量', en: 'Electricity sold' },
  dirIn: { zh: '直接排放', en: 'Direct emissions' },
  bench: { zh: '电力基准值', en: 'Electricity benchmark' },
  result: { zh: '碳排放责任', en: 'Carbon responsibility' },
  preset: { zh: '代入原表', en: 'Load from the table' },
  noUpstream: { zh: '此处上游投入责任取 0（光伏电厂的情形）；其他电厂还要加上燃料按基准值计的责任。', en: 'Upstream input responsibility is taken as 0 here (the photovoltaic case); other plants add their fuel at its benchmark.' },
  note: { zh: '负的责任量是分配结果，不代表物理上的碳移除。', en: 'A negative responsibility is an allocation result, not physical carbon removal.' },
}

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const ROSE = '#ef7a7a'
const SKY = '#74a9f7'

type Plant = { no: string; fuel: string; mode: string; capacity: string; power: number; direct: number; resp: number; perKwh: number }

/** Read the plant rows by header names, so a table with another column order still works. */
function parsePlants(rows: string[][]): Plant[] {
  const out: Plant[] = []
  for (const r of rows) {
    const nums = r.map(cellNumber)
    if (r.length < 9 || cellNumber(r[0]) == null) continue
    const tail = nums.slice(-4)
    if (tail.some((x) => x == null)) continue
    out.push({ no: r[0], fuel: r[1], mode: r[2], capacity: r[3], power: tail[0]!, direct: tail[1]!, resp: tail[2]!, perKwh: tail[3]! })
  }
  return out
}

const fuelColor = (fuel: string) => (/光伏|solar|pv|风|wind/i.test(fuel) ? MINT : /气|gas/i.test(fuel) ? SKY : AMBER)

export default function PlantChart({ table, factors }: { table: Exhibit; factors?: Exhibit }) {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const plants = useMemo(() => parsePlants(table.rows ?? []).sort((a, b) => b.perKwh - a.perKwh), [table])
  const benchmark = useMemo(() => {
    for (const r of factors?.rows ?? []) {
      const i = r.findIndex((c) => /gCO2\/kWh/i.test(c))
      if (i > 0 && cellNumber(r[i - 1]) != null) return cellNumber(r[i - 1])!
    }
    return null
  }, [factors])
  const [hot, setHot] = useState<string | null>(null)
  const [elec, setElec] = useState(6.7) // 亿 kWh
  const [dir, setDir] = useState(0) // 万 tCO2
  const [bench, setBench] = useState(benchmark ?? 630)

  if (!plants.length) return null
  const max = Math.max(...plants.map((p) => Math.abs(p.perKwh)), benchmark ?? 0)
  const H = 150
  const scale = (v: number) => (Math.abs(v) / max) * H
  // 亿kWh × gCO2/kWh = 1e8 × 1e-6 tCO2 = 100 tCO2 = 0.01 万tCO2
  const result = dir - elec * bench * 0.01
  const sel = plants.find((p) => p.no === hot) ?? null

  return (
    <div>
      <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.kicker)}</div>
      <h2 className="display text-[1.7rem] md:text-[2.2rem] leading-[1.12] mt-3 max-w-[22em]">{t(C.title)}</h2>
      <p className="mt-3 text-[14px] text-mute max-w-[640px]">{t(C.lead)}</p>

      <div className="mt-8 grid lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-6">
        {/* chart */}
        <div className="panel rounded-sm p-5 md:p-7">
          <div className="flex items-baseline justify-between gap-3">
            <span className="mono text-[10.5px] tracking-[0.18em] uppercase text-mute">{t(C.perKwh)} · gCO₂/kWh</span>
            {benchmark != null && (
              <span className="mono text-[10.5px] text-amber">
                {t(C.benchmark)} {benchmark} gCO₂/kWh
              </span>
            )}
          </div>
          <div className="relative mt-4" style={{ height: H * 2 + 96 }}>
            <div className="absolute inset-x-0 mono text-[9.5px] text-rose/80" style={{ top: 0 }}>{t(C.above)}</div>
            <div className="absolute inset-x-0 mono text-[9.5px] text-mint/80" style={{ bottom: 0 }}>{t(C.below)}</div>
            <div className="absolute inset-x-0 border-t border-line-2" style={{ top: H + 48 }} />
            <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${plants.length}, minmax(0, 1fr))` }}>
              {plants.map((p, i) => {
                const pos = p.perKwh >= 0
                const h = Math.max(3, scale(p.perKwh))
                const col = pos ? ROSE : MINT
                const active = hot === p.no
                return (
                  <button
                    key={p.no}
                    onMouseEnter={() => setHot(p.no)}
                    onMouseLeave={() => setHot(null)}
                    onFocus={() => setHot(p.no)}
                    onBlur={() => setHot(null)}
                    onClick={() => {
                      setElec(p.power)
                      setDir(p.direct)
                    }}
                    className={`relative h-full transition-opacity ${hot && !active ? 'opacity-45' : ''}`}
                    aria-label={`${t(C.plant)} ${p.no} ${p.fuel} ${p.perKwh} gCO2/kWh`}
                  >
                    <motion.div
                      initial={reduce ? false : { height: 0 }}
                      whileInView={{ height: h }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.8, ease: [0.2, 0.7, 0.2, 1], delay: i * 0.07 }}
                      className="absolute left-1/2 -translate-x-1/2 w-[38%] max-w-[46px] rounded-[2px]"
                      style={{
                        ...(pos ? { bottom: H + 48 } : { top: H + 48 }),
                        height: reduce ? h : undefined,
                        background: `linear-gradient(${pos ? '0deg' : '180deg'}, ${col}33, ${col})`,
                        boxShadow: active ? `0 0 22px ${col}88` : 'none',
                      }}
                    />
                    <div
                      className="absolute left-1/2 -translate-x-1/2 mono tabular text-[12px]"
                      style={{ color: col, ...(pos ? { bottom: H + 48 + h + 6 } : { top: H + 48 + h + 6 }) }}
                    >
                      {p.perKwh > 0 ? '+' : ''}{p.perKwh}
                    </div>
                    <div
                      className="absolute left-1/2 -translate-x-1/2 flex flex-col items-center"
                      style={pos ? { top: H + 54 } : { bottom: H + 54 }}
                    >
                      <FuelIcon fuel={p.fuel} size={30} style={{ color: fuelColor(p.fuel) }} />
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
          <div className="mt-2 grid" style={{ gridTemplateColumns: `repeat(${plants.length}, minmax(0, 1fr))` }}>
            {plants.map((p) => (
              <div key={p.no} className="text-center min-w-0 px-0.5">
                <div className="text-[11.5px] text-ink/90 truncate">{p.fuel}</div>
                <div className="mono text-[9.5px] text-faint truncate">#{p.no} · {p.capacity} MW</div>
              </div>
            ))}
          </div>
          <div className="hairline mt-5 pt-4 min-h-[3.4rem] grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2">
            {(sel ?? plants[plants.length - 1]) &&
              (() => {
                const p = sel ?? plants[plants.length - 1]
                const dpk = p.power ? Math.round((p.direct / p.power) * 100) : 0
                return (
                  <>
                    <Fact k={`${t(C.plant)} #${p.no}`} v={`${p.fuel} ${p.mode !== '-' ? p.mode : ''}`} />
                    <Fact k={t(C.power)} v={`${p.power} 亿kWh`} />
                    <Fact k={t(C.direct)} v={`${p.direct} 万tCO₂ · ${dpk} g/kWh`} />
                    <Fact k={t(C.resp)} v={`${p.resp} 万tCO₂`} color={p.resp >= 0 ? ROSE : MINT} />
                  </>
                )
              })()}
          </div>
        </div>

        {/* calculator */}
        <div className="panel rounded-sm p-5 md:p-7 flex flex-col">
          <div className="mono text-[10.5px] tracking-[0.18em] uppercase text-mint/80">{t(C.calc)}</div>
          <p className="mt-2 text-[12.5px] text-mute leading-relaxed">{t(C.calcSub)}</p>
          <div className="mt-5 space-y-5">
            <Slider label={t(C.dirIn)} unit="万tCO₂" value={dir} min={0} max={1300} step={1} onChange={setDir} color={ROSE} />
            <Slider label={t(C.elec)} unit="亿kWh" value={elec} min={0} max={160} step={0.1} onChange={setElec} color={SKY} />
            <Slider label={t(C.bench)} unit="gCO₂/kWh" value={bench} min={300} max={900} step={1} onChange={setBench} color={AMBER} />
          </div>
          <div className="mt-6 mono text-[11.5px] text-mute leading-relaxed">
            <span className="text-rose">{dir}</span> − <span className="text-sky">{elec}</span> × <span className="text-amber">{bench}</span> × 0.01 =
          </div>
          <div className="mt-1 flex items-baseline gap-3">
            <motion.span
              key={result >= 0 ? 'p' : 'n'}
              initial={reduce ? false : { scale: 0.96 }}
              animate={{ scale: 1 }}
              className="display tabular text-[2.8rem] leading-none"
              style={{ color: result >= 0 ? ROSE : MINT }}
            >
              {result > 0 ? '+' : ''}{result.toFixed(1)}
            </motion.span>
            <span className="mono text-[11px] text-mute">万tCO₂ · {t(C.result)}</span>
          </div>
          <div className="mt-4 flex flex-wrap gap-1.5">
            <span className="mono text-[10px] text-faint mr-1 self-center">{t(C.preset)}</span>
            {plants.map((p) => (
              <button
                key={p.no}
                onClick={() => {
                  setElec(p.power)
                  setDir(p.direct)
                  if (benchmark != null) setBench(benchmark)
                }}
                className="mono text-[10.5px] border border-line-2 rounded-full px-2 py-0.5 text-mute hover:text-ink hover:border-mint/40 transition-colors"
              >
                #{p.no} {p.fuel}
              </button>
            ))}
          </div>
          <p className="mt-auto pt-5 text-[11.5px] text-faint leading-relaxed">{t(C.noUpstream)} {t(C.note)}</p>
        </div>
      </div>
      <div className="mt-3 mono text-[10.5px] text-faint break-words">
        {t(C.source)} {table.path.split('/').pop()} · {table.loc}
      </div>
    </div>
  )
}

function Fact({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div className="min-w-0">
      <div className="mono text-[9.5px] tracking-wide uppercase text-faint">{k}</div>
      <div className="mono text-[11.5px] mt-0.5 truncate" style={{ color: color ?? '#e9efe9' }}>{v}</div>
    </div>
  )
}

function Slider({ label, unit, value, min, max, step, onChange, color }: { label: string; unit: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; color: string }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[12.5px] text-ink/90">{label}</span>
        <span className="mono tabular text-[12.5px]" style={{ color }}>
          {value} <span className="text-[10px] text-faint">{unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="tk-range mt-2 w-full"
        style={{ ['--fill' as string]: color, ['--pct' as string]: `${((value - min) / (max - min)) * 100}%` }}
      />
    </label>
  )
}

import { useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { useT } from '../lib/i18n'
import type { Exhibit } from '../lib/data'
import { Car, Household, Mine, Molecule } from './ClimateIcons'

/**
 * The supply-chain example of the materials as a picture: three producers of one product emit
 * differently, the benchmark is their average, and each one's responsibility is its distance
 * from that benchmark. The numbers are read out of the exported passages.
 */

const C = {
  kicker: { zh: '原文算例 · 产业链上的责任传递', en: 'From the materials · responsibility along a supply chain' },
  title: { zh: '基准值是行业平均，责任是与平均的差距', en: 'The benchmark is the industry average; responsibility is the distance from it' },
  producers: { zh: '铁矿石生产商', en: 'Iron ore producers' },
  direct: { zh: '直接排放', en: 'Direct emissions' },
  resp: { zh: '碳排放责任', en: 'Responsibility' },
  benchmark: { zh: '基准值', en: 'Benchmark' },
  perUnit: { zh: 'kgCO₂/单位', en: 'kgCO₂ / unit' },
  sum: { zh: '行业合计', en: 'Industry total' },
  zero: { zh: '全行业责任加总为零', en: 'Responsibilities across the industry sum to zero' },
  chain: { zh: '责任随产品向下游传递', en: 'Responsibility travels downstream with the product' },
  ore: { zh: '铁矿石', en: 'Iron ore' },
  car: { zh: '汽车', en: 'Cars' },
  consumer: { zh: '终端消费者', en: 'Final consumers' },
  carBench: { zh: '汽车基准值', en: 'Car benchmark' },
  consumerResp: { zh: '消费者承担', en: 'Borne by consumers' },
  equals: { zh: '等于上游所有生产者直接排放之和', en: 'equal to the direct emissions of all upstream producers' },
  source: { zh: '数据取自', en: 'Data from' },
  pick: { zh: '点击生产商查看', en: 'Select a producer' },
  better: { zh: '低于行业平均', en: 'below the industry average' },
  worse: { zh: '高于行业平均', en: 'above the industry average' },
  even: { zh: '等于行业平均', en: 'equal to the industry average' },
}

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const ROSE = '#ef7a7a'

/** "90+110+100=300" → [90, 110, 100]; the first such sum in the passage. */
function firstSum(text: string): number[] {
  const m = text.match(/(\d+(?:\+\d+){1,5})\s*=\s*\d+/)
  return m ? m[1].split('+').map(Number) : []
}
const firstNumberBefore = (text: string, unit: RegExp) => {
  const m = text.match(new RegExp(`(\\d+(?:\\.\\d+)?)\\s*${unit.source}`))
  return m ? Number(m[1]) : null
}

export default function ChainFlow({ basis, totals }: { basis: Exhibit; totals: Exhibit }) {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const [sel, setSel] = useState(1)
  const emissions = firstSum(basis.text)
  if (emissions.length < 2) return null
  const benchmark = emissions.reduce((a, b) => a + b, 0) / emissions.length
  const carBench = (() => {
    // "(780+2.9×1800)/3=2000 kgCO2": the benchmark stated as the result of a division
    const m = basis.text.match(/\/\s*\d+\s*=\s*(\d+(?:\.\d+)?)\s*kgCO2/i)
    return m ? Number(m[1]) : null
  })()
  const consumer = firstNumberBefore(totals.text.slice(totals.text.indexOf('消费者')), /\s*kgCO2/)
  const max = Math.max(...emissions) * 1.15
  const names = ['A', 'B', 'C', 'D', 'E', 'F']
  const cur = emissions[sel] - benchmark

  return (
    <div>
      <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.kicker)}</div>
      <h2 className="display text-[1.7rem] md:text-[2.2rem] leading-[1.12] mt-3 max-w-[22em]">{t(C.title)}</h2>

      <div className="mt-8 grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-6">
        {/* producers vs benchmark */}
        <div className="panel rounded-sm p-5 md:p-7">
          <div className="flex items-baseline justify-between gap-3">
            <span className="mono text-[10.5px] tracking-[0.18em] uppercase text-mute">{t(C.producers)}</span>
            <span className="mono text-[10.5px] text-faint">{t(C.perUnit)}</span>
          </div>
          <div className="relative mt-6 h-[210px]">
            <div className="absolute inset-x-0 border-t border-dashed border-amber/70" style={{ bottom: `${(benchmark / max) * 100}%` }}>
              <span className="absolute right-0 -top-5 mono text-[10.5px] text-amber">
                {t(C.benchmark)} {benchmark}
              </span>
            </div>
            <div className="absolute inset-0 grid items-end" style={{ gridTemplateColumns: `repeat(${emissions.length}, minmax(0, 1fr))` }}>
              {emissions.map((e, i) => {
                const d = e - benchmark
                const col = d > 0 ? ROSE : d < 0 ? MINT : AMBER
                return (
                  <button key={i} onClick={() => setSel(i)} className={`relative h-full flex flex-col justify-end items-center transition-opacity ${sel === i ? '' : 'opacity-55 hover:opacity-90'}`} aria-label={`${names[i]} ${e}`}>
                    <div className="relative w-[46%] max-w-[64px]">
                      {!reduce && (
                        <span className="plume absolute left-1/2 -translate-x-1/2 -top-3 text-mute" style={{ animationDelay: `${i * 0.7}s` }}>
                          <Molecule size={18} />
                        </span>
                      )}
                      <motion.div
                        initial={reduce ? false : { height: 0 }}
                        whileInView={{ height: (e / max) * 210 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8, ease: [0.2, 0.7, 0.2, 1], delay: i * 0.1 }}
                        className="w-full rounded-t-[2px]"
                        style={{ height: reduce ? (e / max) * 210 : undefined, background: `linear-gradient(0deg, ${col}22, ${col}cc)`, boxShadow: sel === i ? `0 0 24px ${col}66` : 'none' }}
                      />
                    </div>
                    <span className="absolute mono tabular text-[12px] text-ink" style={{ bottom: `calc(${(e / max) * 100}% + 26px)` }}>{e}</span>
                  </button>
                )
              })}
            </div>
          </div>
          <div className="mt-3 grid" style={{ gridTemplateColumns: `repeat(${emissions.length}, minmax(0, 1fr))` }}>
            {emissions.map((e, i) => {
              const d = e - benchmark
              return (
                <div key={i} className="text-center">
                  <Mine size={26} className="mx-auto" style={{ color: sel === i ? '#e9efe9' : '#5e6a63' }} />
                  <div className="mono text-[11px] text-mute mt-1">{names[i]}</div>
                  <div className="display tabular text-[1.25rem] leading-none mt-1.5" style={{ color: d > 0 ? ROSE : d < 0 ? MINT : AMBER }}>
                    {d > 0 ? '+' : ''}{d}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="hairline mt-5 pt-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
            <span className="text-[12.5px] text-mute">
              {names[sel]}: {emissions[sel]} − {benchmark} ={' '}
              <span style={{ color: cur > 0 ? ROSE : cur < 0 ? MINT : AMBER }}>{cur > 0 ? '+' : ''}{cur}</span>{' '}
              <span className="text-faint">· {t(cur > 0 ? C.worse : cur < 0 ? C.better : C.even)}</span>
            </span>
            <span className="mono text-[11px] text-mint">
              {t(C.sum)} {emissions.map((e) => e - benchmark).map((d) => (d > 0 ? `+${d}` : `${d}`)).join(' ')} = 0
            </span>
          </div>
        </div>

        {/* the chain */}
        <div className="panel rounded-sm p-5 md:p-7 flex flex-col">
          <span className="mono text-[10.5px] tracking-[0.18em] uppercase text-mute">{t(C.chain)}</span>
          <div className="relative flex-1 min-h-[250px] mt-4">
            <svg viewBox="0 0 600 250" className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid meet" aria-hidden>
              <defs>
                <linearGradient id="cf" x1="0" x2="1">
                  <stop offset="0" stopColor={AMBER} stopOpacity="0.15" />
                  <stop offset="1" stopColor={AMBER} stopOpacity="0.75" />
                </linearGradient>
              </defs>
              {/* widening ribbon: responsibility accumulates downstream */}
              <path d="M110 118 C 190 118, 210 108, 290 106 L 290 144 C 210 142, 190 132, 110 132 Z" fill="url(#cf)" opacity="0.5" />
              <path d="M330 96 C 400 96, 420 84, 490 80 L 490 170 C 420 166, 400 154, 330 154 Z" fill="url(#cf)" opacity="0.7" />
              <path d="M112 125 H288" stroke={AMBER} strokeWidth="1.4" className={reduce ? '' : 'flow-right'} />
              <path d="M332 125 H488" stroke={AMBER} strokeWidth="1.4" className={reduce ? '' : 'flow-right'} />
              {[70, 310, 530].map((x) => (
                <circle key={x} cx={x} cy={125} r={40} fill="#0a0f0d" stroke="rgba(214,234,223,0.18)" />
              ))}
            </svg>
            <div className="absolute inset-0 grid grid-cols-3 items-center text-center">
              <Node icon={<Mine size={34} />} label={t(C.ore)} top={`${t(C.benchmark)} ${benchmark}`} />
              <Node icon={<Car size={34} />} label={t(C.car)} top={carBench != null ? `${t(C.carBench)} ${carBench.toLocaleString('en-US')}` : ''} />
              <Node icon={<Household size={34} />} label={t(C.consumer)} top="" accent />
            </div>
          </div>
          {consumer != null && (
            <div className="hairline pt-4 mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-[12.5px] text-mute">{t(C.consumerResp)}</span>
              <span className="display tabular text-[2.2rem] leading-none text-amber">{consumer.toLocaleString('en-US')}</span>
              <span className="mono text-[11px] text-mute">kgCO₂</span>
              <span className="text-[12px] text-faint">{t(C.equals)}</span>
            </div>
          )}
        </div>
      </div>
      <div className="mt-3 mono text-[10.5px] text-faint break-words">
        {t(C.source)} {basis.path.split('/').pop()} · {basis.loc}
      </div>
    </div>
  )
}

function Node({ icon, label, top, accent = false }: { icon: React.ReactNode; label: string; top: string; accent?: boolean }) {
  return (
    <div className="flex flex-col items-center">
      <div className="mono text-[10px] text-amber h-4">{top}</div>
      <div className="h-[84px] flex items-center justify-center" style={{ color: accent ? '#efb75a' : '#e9efe9' }}>{icon}</div>
      <div className="text-[12.5px] text-ink/90">{label}</div>
    </div>
  )
}

/**
 * How the summer is going, written for the student.
 *
 * A parent wants to know where a child sits against their year group. A child
 * wants to know whether the work is paying off, which is a different question
 * and a kinder one. So this charts their own scores against their own earlier
 * scores and says plainly whether the line is going up — no year averages, no
 * ranking, nothing they cannot do anything about.
 */

import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { ChildProgress } from '../api/types'
import { Card, EmptyState, SectionTitle, subjectIcon } from './ui'

/** Enough results that a change between halves means something. */
const ENOUGH_TO_SPOT_A_TREND = 4

interface Point {
  date: string
  day: string
  score: number
  label: string
  subject: string
}

function useJourney(progress: ChildProgress): Point[] {
  return useMemo(
    () =>
      progress.scoreLog
        .filter((entry) => entry.scorePct != null)
        .map((entry) => ({
          date: entry.recordedAt,
          day: new Date(entry.recordedAt).toLocaleDateString('en-GB', {
            day: 'numeric',
            month: 'short',
          }),
          score: entry.scorePct as number,
          label: entry.label,
          subject: entry.subject,
        }))
        .sort((a, b) => a.date.localeCompare(b.date)),
    [progress.scoreLog],
  )
}

/**
 * Whether the recent half is beating the earlier half.
 *
 * Deliberately blunt: comparing halves is easy to explain to a twelve year old,
 * where a regression line is not.
 */
function trendOf(points: Point[]): { text: string; tone: string } | null {
  if (points.length < ENOUGH_TO_SPOT_A_TREND) return null

  const middle = Math.floor(points.length / 2)
  const mean = (list: Point[]) => list.reduce((sum, p) => sum + p.score, 0) / list.length
  const shift = Math.round(mean(points.slice(middle)) - mean(points.slice(0, middle)))

  if (shift >= 3) {
    return {
      text: `Your recent work is ${shift} points better than when you started. Keep going.`,
      tone: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    }
  }
  if (shift <= -3) {
    return {
      text: `Your recent scores are ${Math.abs(shift)} points below your earlier ones. Worth slowing down on the next one.`,
      tone: 'border-amber-200 bg-amber-50 text-amber-900',
    }
  }
  return {
    text: 'You are holding steady across the summer.',
    tone: 'border-slate-200 bg-slate-50 text-slate-700',
  }
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-slate-900">{Math.round(point.score)}%</div>
      <div className="mt-0.5 max-w-[220px] text-slate-600">{point.label}</div>
      <div className="text-slate-400">{point.day}</div>
    </div>
  )
}

export function SummerProgress({ progress }: { progress: ChildProgress }) {
  const points = useJourney(progress)
  const trend = trendOf(points)

  const average = useMemo(
    () =>
      points.length
        ? Math.round(points.reduce((sum, p) => sum + p.score, 0) / points.length)
        : null,
    [points],
  )

  const best = useMemo(() => {
    const scored = progress.subjects.filter((s) => s.averageScore != null)
    if (!scored.length) return null
    return scored.reduce((top, s) => ((s.averageScore ?? 0) > (top.averageScore ?? 0) ? s : top))
  }, [progress.subjects])

  if (points.length === 0) {
    return (
      <section>
        <SectionTitle title="Your summer so far" />
        <EmptyState
          icon="📈"
          title="No marks yet"
          body="Hand in a piece of work and your scores will start showing up here."
        />
      </section>
    )
  }

  return (
    <section>
      <SectionTitle
        title="Your summer so far"
        subtitle={`${points.length} piece${points.length === 1 ? '' : 's'} of work marked`}
      />

      <Card>
        <div className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <div>
            <div className="text-3xl font-bold text-slate-900">{average}%</div>
            <div className="text-xs text-slate-500">average so far</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-slate-900">
              {Math.round(Math.max(...points.map((p) => p.score)))}%
            </div>
            <div className="text-xs text-slate-500">your best</div>
          </div>
          {best && (
            <div>
              <div className="text-xl font-bold text-slate-900">
                {subjectIcon(best.subject)} {best.subject}
              </div>
              <div className="text-xs text-slate-500">going best at {Math.round(best.averageScore as number)}%</div>
            </div>
          )}
        </div>

        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={points} margin={{ top: 8, right: 8, left: -22, bottom: 4 }}>
            <defs>
              <linearGradient id="summerFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="day" tick={{ fontSize: 11 }} tickMargin={6} />
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 11 }} />
            <Tooltip content={<ChartTooltip />} />
            {average != null && (
              <ReferenceLine
                y={average}
                stroke="#94a3b8"
                strokeDasharray="4 4"
                label={{ value: 'average', position: 'right', fontSize: 10, fill: '#94a3b8' }}
              />
            )}
            <Area
              type="monotone"
              dataKey="score"
              stroke="#0ea5e9"
              strokeWidth={2.5}
              fill="url(#summerFill)"
              dot={{ r: 4, fill: '#0ea5e9' }}
              activeDot={{ r: 6 }}
            />
          </AreaChart>
        </ResponsiveContainer>

        {trend && (
          <div className={`mt-3 rounded-xl border px-4 py-2.5 text-sm ${trend.tone}`}>
            {trend.text}
          </div>
        )}
      </Card>
    </section>
  )
}

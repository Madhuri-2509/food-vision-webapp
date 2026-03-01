import { useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts'

const MACRO_COLORS = {
  protein: '#f59e0b', 
  carbs: '#10b981',   
  fat: '#f43f5e',     
}

export default function MacroChart({ calories, protein, carbs, fat }) {
  const totalGrams = protein + carbs + fat || 1

  const pieData = useMemo(() => {
    const raw = [
      { name: 'Protein', value: Number(protein) || 0, color: MACRO_COLORS.protein },
      { name: 'Carbs', value: Number(carbs) || 0, color: MACRO_COLORS.carbs },
      { name: 'Fat', value: Number(fat) || 0, color: MACRO_COLORS.fat },
    ]
    const hasAny = raw.some((d) => d.value > 0)
    if (!hasAny) return [{ name: 'No data', value: 1, color: '#94a3b8' }]
    return raw.filter((d) => d.value > 0)
  }, [protein, carbs, fat])

  const barData = useMemo(
    () => [
      { name: 'Protein', grams: Number(protein) || 0, fill: MACRO_COLORS.protein },
      { name: 'Carbs', grams: Number(carbs) || 0, fill: MACRO_COLORS.carbs },
      { name: 'Fat', grams: Number(fat) || 0, fill: MACRO_COLORS.fat },
    ],
    [protein, carbs, fat]
  )

  const hasMacroData = totalGrams > 0

  return (
    <motion.div
      className="space-y-4"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <p className="text-slate-600 font-medium">
        Calories:{' '}
        <span className="text-slate-900 text-lg font-semibold">
          {Number(calories).toFixed(0)}
        </span>{' '}
        kcal
      </p>
      <div className="grid grid-cols-3 gap-2 text-xs sm:text-sm">
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 flex flex-col items-start">
          <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            Protein
          </span>
          <span className="text-slate-900 font-semibold">
            {Number(protein).toFixed(0)}g
          </span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 flex flex-col items-start">
          <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Carbs
          </span>
          <span className="text-slate-900 font-semibold">
            {Number(carbs).toFixed(0)}g
          </span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 flex flex-col items-start">
          <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-rose-500" />
            Fat
          </span>
          <span className="text-slate-900 font-semibold">
            {Number(fat).toFixed(0)}g
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-2">
        <div className="min-h-[220px] flex flex-col">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Macro distribution
          </p>
          {hasMacroData ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={56}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                  isAnimationActive
                  animationDuration={600}
                  animationBegin={0}
                  label={({ name, value }) =>
                    value > 0 ? `${name} ${value.toFixed(0)}g` : null
                  }
                  labelLine={false}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => [`${Number(value).toFixed(1)}g`, '']}
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex-1 flex items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50/50 text-slate-400 text-sm">
              No macro data
            </div>
          )}
        </div>
        <div className="min-h-[220px] flex flex-col">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Macros (grams)
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={barData}
              margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
              layout="vertical"
            >
              <XAxis type="number" hide={!hasMacroData} />
              <YAxis
                type="category"
                dataKey="name"
                width={56}
                tick={{ fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(value) => [`${Number(value).toFixed(1)}g`, '']}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                cursor={{ fill: 'rgba(148, 163, 184, 0.1)' }}
              />
              {hasMacroData && <Legend />}
              <Bar
                dataKey="grams"
                name="grams"
                fill="#10b981"
                radius={[0, 4, 4, 0]}
                isAnimationActive
                animationDuration={600}
                animationBegin={0}
              >
                {barData.map((entry, index) => (
                  <Cell key={`bar-${index}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </motion.div>
  )
}

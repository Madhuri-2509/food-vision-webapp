export default function MacroChart({ calories, protein, carbs, fat }) {
  const total = protein + carbs + fat || 1

  return (
    <div className="space-y-3">
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
            {protein.toFixed(0)}g
          </span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 flex flex-col items-start">
          <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Carbs
          </span>
          <span className="text-slate-900 font-semibold">
            {carbs.toFixed(0)}g
          </span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 flex flex-col items-start">
          <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-rose-500" />
            Fat
          </span>
          <span className="text-slate-900 font-semibold">
            {fat.toFixed(0)}g
          </span>
        </div>
      </div>
    </div>
  )
}

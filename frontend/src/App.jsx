import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Toaster, toast } from 'react-hot-toast'
import ImageUploader from './components/ImageUploader'
import MacroChart from './components/MacroChart'
import foodAnimation from './Lottie-Animations/Food.json'
import foodCountAnimation from './Lottie-Animations/food-count.json'
import fitnessAnimation from './Lottie-Animations/fitness.json'
import sandyLoadingAnimation from './Lottie-Animations/Sandy Loading.json'
import paperplaneLoadingAnimation from './Lottie-Animations/Loading 40 _ Paperplane.json'
import catPlayingAnimation from './Lottie-Animations/Cat playing animation.json'

const API_BASE = '/api'
const DEEP_SCAN_UNAVAILABLE_MSG = 'Deep Scan engine is currently unavailable. Please use Fast Scan.'
const LOADING_ANIMATIONS = [
  foodAnimation,
  foodCountAnimation,
  fitnessAnimation,
  sandyLoadingAnimation,
  paperplaneLoadingAnimation,
  catPlayingAnimation,
]

function SegmentationOverlay({ imageUrl, regions }) {
  const [size, setSize] = useState({ w: 1, h: 1 })
  const onLoad = useCallback((e) => {
    const img = e.target
    if (img?.naturalWidth) setSize({ w: img.naturalWidth, h: img.naturalHeight })
  }, [])
  if (!regions?.length) return null
  return (
    <div className="relative inline-block w-full max-w-md">
      <img
        src={imageUrl}
        alt="With regions"
        className="w-full h-auto rounded-lg border border-slate-200"
        onLoad={onLoad}
      />
      <div className="absolute inset-0 pointer-events-none">
        {regions.map((r, i) => {
          const [x1, y1, x2, y2] = r.bbox || [0, 0, 0, 0]
          const left = (x1 / size.w) * 100
          const top = (y1 / size.h) * 100
          const width = ((x2 - x1) / size.w) * 100
          const height = ((y2 - y1) / size.h) * 100
          return (
            <div
              key={i}
              className="absolute border-2 border-emerald-400 bg-emerald-400/20 rounded"
              style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
            />
          )
        })}
      </div>
    </div>
  )
}

export default function App() {

  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [correcting, setCorrecting] = useState(false)
  const [overrideLabel, setOverrideLabel] = useState('')

  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('')
  const [scanMode, setScanMode] = useState('fast')
  const detectionCountRef = useRef(0)

  const SSE_TIMEOUT_MS = scanMode === 'deep' ? 150000 : 90000

  const handleUpload = async (file) => {
    detectionCountRef.current += 1
    const loadingToastId = toast.loading(scanMode === 'deep' ? 'Deep scanning…' : 'Analyzing image…')
    setLoading(true)
    setError(null)
    setResult(null)
    setProgress(0)
    setStage('Uploading…')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('scan_mode', scanMode)

    let res
    try {
      res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData })
    } catch (e) {
      toast.error(e.message || 'Upload failed')
      toast.dismiss(loadingToastId)
      setError(e.message || 'Upload failed')
      setLoading(false)
      setStage('')
      return
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      const msg = res.status === 503 ? DEEP_SCAN_UNAVAILABLE_MSG : (err.detail || res.statusText || 'Upload failed')
      toast.error(msg)
      toast.dismiss(loadingToastId)
      setError(msg)
      setLoading(false)
      setStage('')
      return
    }

    let data
    try {
      data = await res.json()
    } catch {
      toast.error('Invalid response')
      toast.dismiss(loadingToastId)
      setError('Invalid response')
      setLoading(false)
      setStage('')
      return
    }

    const jobId = data.job_id
    if (!jobId) {
      toast.error('Server did not return a job ID')
      toast.dismiss(loadingToastId)
      setError('Server did not return a job ID')
      setLoading(false)
      setStage('')
      return
    }

    setStage('Analyzing…')
    const eventSource = new EventSource(`${API_BASE}/jobs/${jobId}/progress`)
    const timeoutId = setTimeout(() => {
      eventSource.close()
      toast.error('Request timed out')
      toast.dismiss(loadingToastId)
      setError('Request timed out')
      setLoading(false)
      setProgress(0)
      setStage('')
    }, SSE_TIMEOUT_MS)

    eventSource.onmessage = (event) => {
      try {
        const d = JSON.parse(event.data)
        if (d.type === 'progress') {
          setStage(d.stage ?? '')
          setProgress(typeof d.progress === 'number' ? d.progress : 0)
        } else if (d.type === 'result') {
          clearTimeout(timeoutId)
          eventSource.close()
          toast.success('Analysis complete!', { id: loadingToastId })
          setResult(d)
          setProgress(100)
          setLoading(false)
          setStage('')
        } else if (d.type === 'error') {
          clearTimeout(timeoutId)
          eventSource.close()
          const msg = (d.message && d.message.includes('unavailable')) ? DEEP_SCAN_UNAVAILABLE_MSG : (d.message || 'Something went wrong')
          toast.error(msg)
          toast.dismiss(loadingToastId)
          setError(msg)
          setLoading(false)
          setStage('')
        }
      } catch {
      }
    }

    eventSource.onerror = () => {
      if (eventSource.readyState === EventSource.CLOSED) return
      clearTimeout(timeoutId)
      eventSource.close()
      toast.error('Connection lost')
      toast.dismiss(loadingToastId)
      setError('Connection lost')
      setLoading(false)
      setStage('')
    }
  }

  const handleCorrect = async () => {
    const label = newLabel?.trim()
    if (!label || !result?.meal_id) return
    setCorrecting(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/correct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meal_id: result.meal_id, new_label: label }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || res.statusText || 'Correct failed')
      }
      const data = await res.json()
      setResult((prev) => ({ ...prev, totals: data.totals, items: data.items }))
      setEditing(false)
      setNewLabel('')
    } catch (e) {
      setError(e.message)
    } finally {
      setCorrecting(false)
    }
  }

  const handleNewEstimation = () => {
    setResult(null)
    setError(null)
    setEditing(false)
    setNewLabel('')
    setOverrideLabel('')
    setProgress(0)
    setLoading(false)
    const fileInput = document.getElementById('image-upload-input')
    if (fileInput) fileInput.value = ''
    toast('Ready for a new scan', { icon: '🔄' })
  }

  const handleForceCorrect = async (label) => {
    const trimmed = (label ?? overrideLabel)?.trim()
    if (!trimmed || !result?.meal_id) return
    setCorrecting(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/correct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meal_id: result.meal_id, new_label: trimmed }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || res.statusText || 'Correct failed')
      }
      const data = await res.json()
      setResult((prev) => ({ ...prev, totals: data.totals, items: data.items }))
      setOverrideLabel('')
    } catch (e) {
      setError(e.message)
    } finally {
      setCorrecting(false)
    }
  }

  const isNonFood = result && (result.items?.length === 0 || result.original_label === 'Non-Food Item Detected')

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] bg-[size:24px_24px] bg-fixed [mask-image:linear-gradient(to_bottom,black_0%,black_28%,transparent_70%)] [-webkit-mask-image:linear-gradient(to_bottom,black_0%,black_28%,transparent_70%)]"
      />
      <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
      <header className="relative z-10 bg-gradient-to-r from-emerald-700/90 via-emerald-600/90 to-teal-600/90 backdrop-blur-md text-white py-4 px-4 sm:px-6 shadow-md shrink-0 border-b border-emerald-500/50">
        <div className="max-w-4xl mx-auto flex items-center gap-3 justify-center">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold truncate">FoodVision</h1>
            <p className="text-emerald-100 text-sm truncate">
              Smart food recognition and macro breakdown
            </p>
          </div>
          <button
            type="button"
            onClick={handleNewEstimation}
            className="inline-flex items-center gap-2 rounded-lg border border-white/60 bg-white/10 px-3 py-2 text-sm font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white/50 focus:ring-offset-2 focus:ring-offset-transparent transition-colors shrink-0"
            aria-label="New estimation"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            New estimation
          </button>
        </div>
      </header >

      <div className="relative z-10 flex flex-1 min-h-0 flex overflow-hidden">
        <main className="flex-1 min-w-0 overflow-y-auto p-6 max-w-4xl mx-auto w-full space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <span className="text-sm font-medium text-slate-600">Scan mode</span>
            <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              <button
                type="button"
                onClick={() => setScanMode('fast')}
                disabled={loading}
                className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${scanMode === 'fast' ? 'bg-emerald-600 text-white shadow' : 'text-slate-600 hover:bg-slate-50'}`}
              >
                Fast Scan (~3s)
              </button>
              <button
                type="button"
                onClick={() => setScanMode('deep')}
                disabled={loading}
                className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${scanMode === 'deep' ? 'bg-emerald-600 text-white shadow' : 'text-slate-600 hover:bg-slate-50'}`}
              >
                Deep Scan (~60s)
              </button>
            </div>
          </div>
          <ImageUploader
            onUpload={handleUpload}
            loading={loading}
            scanMode={scanMode}
            loadingAnimation={loading && !result ? (scanMode === 'deep' ? sandyLoadingAnimation : LOADING_ANIMATIONS[detectionCountRef.current % LOADING_ANIMATIONS.length]) : null}
            loadingAnimationKey={detectionCountRef.current}
          />
          {error && (
            <div className="rounded-lg bg-red-100 text-red-800 px-4 py-3 text-sm sm:text-base">
              {error}
            </div>
          )}

          {loading && !result && (
            <div className="rounded-xl bg-white shadow p-5 sm:p-6 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-slate-600 font-medium">{stage || 'Analyzing…'}</span>
                <span className="text-slate-500 tabular-nums">{Math.round(progress)}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-[width] duration-150 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          <AnimatePresence mode="wait">
            {result && (
              <>
                <motion.section
                  key="segmentation"
                  className="rounded-2xl bg-white shadow-md border border-slate-200/80 overflow-hidden transition-shadow hover:shadow-lg"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/80">
                    <h2 className="text-base font-semibold text-slate-700 tracking-tight">Segmentation</h2>
                    <p className="text-xs text-slate-500 mt-0.5">Detected regions in your image</p>
                  </div>
                  <div className="p-5 space-y-4">
                    {result.annotated_image_url ? (
                      <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-100/50">
                        <img
                          src={result.annotated_image_url}
                          alt="Segmentation overlay"
                          className="w-full h-auto object-contain max-h-96"
                        />
                        <p className="text-xs text-slate-500 px-3 py-2 bg-slate-50/80">
                          Boxes and labels drawn with supervision
                        </p>
                      </div>
                    ) : result.regions?.length > 0 && result.image_url ? (
                      <SegmentationOverlay imageUrl={result.image_url} regions={result.regions} />
                    ) : result.image_url ? (
                      <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-100/50">
                        <img
                          src={result.image_url}
                          alt="Analyzed"
                          className="w-full h-auto object-contain max-h-80"
                        />
                      </div>
                    ) : null}
                    {result.items?.some((i) => i.segment_image_url) && (
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        {result.items.map((item, idx) => (
                          <div key={idx} className="rounded-xl border border-slate-200 overflow-hidden bg-white shadow-sm">
                            <img
                              src={item.segment_image_url || result.image_url}
                              alt={item.name}
                              className="w-full h-28 object-cover"
                            />
                            <div className="p-3 text-center">
                              <p className="font-medium text-slate-800 capitalize text-sm">
                                {item.name.replace(/_/g, ' ')}
                              </p>
                              <p className="text-xs text-emerald-600 font-medium mt-0.5">
                                {Math.round(item.macros?.calories ?? 0)} cal
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {!result.annotated_image_url && !result.image_url && (
                      <p className="text-slate-500 text-sm">No image available</p>
                    )}
                  </div>
                </motion.section>

                <motion.section
                  key="result"
                  className="rounded-2xl bg-white shadow-md border border-slate-200/80 overflow-hidden transition-shadow hover:shadow-lg"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-emerald-50/90 to-teal-50/80">
                    <div className="flex justify-between items-center gap-3 flex-wrap">
                      <div>
                        <h2 className="text-base font-semibold text-slate-800 tracking-tight">Nutrition result</h2>
                        <p className="text-xs text-slate-500 mt-0.5">Macros and detected items</p>
                      </div>
                      {!isNonFood && !editing && (
                        <button
                          type="button"
                          onClick={() => { setEditing(true); setNewLabel(result.items?.[0]?.name ?? ''); setError(null) }}
                          className="text-sm text-emerald-700 hover:text-emerald-800 font-medium px-3 py-1.5 rounded-lg hover:bg-emerald-100/80 transition-colors"
                        >
                          Edit label
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="p-5 space-y-6">
                    {editing && !isNonFood && (
                      <div className="flex gap-2 flex-wrap items-center p-4 rounded-xl bg-slate-50 border border-slate-200">
                        <input
                          type="text"
                          value={newLabel}
                          onChange={(e) => setNewLabel(e.target.value)}
                          placeholder="e.g. Dosa"
                          className="flex-1 min-w-[140px] rounded-lg border border-slate-300 px-3 py-2.5 text-slate-800 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 text-sm"
                          disabled={correcting}
                        />
                        <button
                          type="button"
                          onClick={handleCorrect}
                          disabled={correcting || !newLabel?.trim()}
                          className="rounded-lg bg-emerald-600 text-white px-4 py-2.5 text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:pointer-events-none transition-colors"
                        >
                          {correcting ? 'Saving…' : 'Save'}
                        </button>
                        <button
                          type="button"
                          onClick={() => { setEditing(false); setNewLabel(''); setError(null) }}
                          disabled={correcting}
                          className="rounded-lg border border-slate-300 text-slate-600 px-4 py-2.5 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    )}

                    {isNonFood && (
                      <div className="bg-amber-50/90 border border-amber-200 rounded-xl p-5 shadow-sm">
                        <div className="flex items-center gap-2 mb-3">
                          <h3 className="text-lg font-bold text-amber-800">No edible food detected</h3>
                        </div>
                        <p className="text-amber-700/90 text-sm mb-4">
                          Our AI didn&apos;t find any recognizable food in this image.
                        </p>
                        <div className="bg-white/80 p-4 rounded-lg border border-amber-200/80">
                          <p className="text-sm text-slate-600 mb-3 font-medium">Think it&apos;s food? Tell us what it is:</p>
                          <div className="flex gap-2 flex-wrap">
                            <input
                              type="text"
                              value={overrideLabel}
                              onChange={(e) => setOverrideLabel(e.target.value)}
                              placeholder="e.g. idli, sambar"
                              className="flex-1 min-w-[140px] border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 text-slate-800"
                              disabled={correcting}
                            />
                            <button
                              type="button"
                              onClick={() => handleForceCorrect(overrideLabel)}
                              disabled={correcting || !overrideLabel?.trim()}
                              className="bg-amber-600 text-white px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-amber-700 transition-colors disabled:opacity-50 disabled:pointer-events-none"
                            >
                              {correcting ? 'Saving…' : 'Force correct'}
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {!isNonFood && result.items?.length > 0 && (
                      <>
                        <div>
                          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Detected items</p>
                          <div className="flex flex-wrap gap-2">
                            {result.items.map((i, idx) => (
                              <span
                                key={idx}
                                className="inline-flex items-center rounded-full bg-emerald-100 text-emerald-800 px-3 py-1 text-sm font-medium"
                              >
                                {i.name.replace(/_/g, ' ')}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                          <div className="px-4 py-3 bg-slate-50 border-b border-slate-200">
                            <h3 className="text-sm font-semibold text-slate-700">Per-item macros</h3>
                          </div>
                          <ul className="divide-y divide-slate-100">
                            {result.items.map((item, idx) => (
                              <li
                                key={idx}
                                className="px-4 py-3.5 flex items-center justify-between gap-3 bg-white hover:bg-slate-50/50 transition-colors text-sm"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="font-medium text-slate-800 capitalize truncate">
                                    {item.name.replace(/_/g, ' ')}
                                  </span>
                                  <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-500 px-2 py-0.5 text-xs tabular-nums">
                                    ×{item.quantity}
                                  </span>
                                </div>
                                <span className="text-slate-600 text-right tabular-nums whitespace-nowrap">
                                  <span className="text-emerald-600 font-medium">
                                    {Math.round(item.macros?.calories ?? 0)} cal
                                  </span>
                                  {' · '}P {Math.round(item.macros?.protein ?? 0)}g
                                  {' · '}C {Math.round(item.macros?.carbs ?? 0)}g
                                  {' · '}F {Math.round(item.macros?.fat ?? 0)}g
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </>
                    )}
                    {!isNonFood && (
                      <div className="pt-1">
                        <MacroChart
                          calories={result.totals?.calories ?? 0}
                          protein={result.totals?.protein ?? 0}
                          carbs={result.totals?.carbs ?? 0}
                          fat={result.totals?.fat ?? 0}
                        />
                      </div>
                    )}
                  </div>
                </motion.section>
              </>
            )}
          </AnimatePresence>
        </main>
      </div>
      <footer className="border-t border-slate-200 bg-slate-100 text-slate-500 text-xs sm:text-sm py-3 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-1.5">
          <span>FoodVision © {new Date().getFullYear()}</span>
          <span className="text-slate-400">
            Built for thesis demo – macros are approximate.
          </span>
        </div>
      </footer>
    </div >
  )
}

import { useCallback, useRef } from 'react'
import Lottie from 'lottie-react'

export default function ImageUploader({ onUpload, loading, scanMode = 'fast', loadingAnimation, loadingAnimationKey }) {
  const inputRef = useRef(null)

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const file = e.dataTransfer?.files?.[0]
    if (file?.type?.startsWith('image/')) onUpload(file)
  }, [onUpload])

  const handleChange = useCallback((e) => {
    const file = e.target?.files?.[0]
    if (file) onUpload(file)
  }, [onUpload])

  const handleDragOver = useCallback((e) => e.preventDefault(), [])

  return (
    <div
      className={`
        border-2 border-dashed rounded-xl p-8 text-center transition-colors
        ${loading ? 'border-amber-400 bg-amber-50' : 'border-slate-300 hover:border-emerald-500 hover:bg-emerald-50/50'}
      `}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <input
        id="image-upload-input"
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
        disabled={loading}
      />
      {loading ? (
        <div className="flex flex-col items-center justify-center space-y-4">
          <p className="text-amber-700 text-sm">
            {scanMode === 'deep' ? 'Deep scanning… isolating and identifying each food item. This may take up to a minute.' : 'Analyzing image… this may take a few seconds.'}
          </p>
          {loadingAnimation && (
            <Lottie
              key={loadingAnimationKey}
              animationData={loadingAnimation}
              loop
              style={{ width: 180, height: 180 }}
            />
          )}
        </div>
      ) : (
        <>
          <p className="text-slate-600 mb-2">Drop a food image here or click to choose</p>
          <button
            type="button"
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
            onClick={() => inputRef.current?.click()}
          >
            Choose file
          </button>
        </>
      )}
    </div>
  )
}

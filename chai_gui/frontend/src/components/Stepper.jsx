import React from 'react'
import { Check } from 'lucide-react'

/**
 * Generic stepper component.
 * Props:
 *   steps   — array of { label }
 *   current — 0-based index of active step
 */
export default function Stepper({ steps, current }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((step, idx) => {
        const done    = idx < current
        const active  = idx === current
        const pending = idx > current

        return (
          <React.Fragment key={idx}>
            {/* Step bubble */}
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all ${
                  done
                    ? 'bg-sky-600 border-sky-600 text-white'
                    : active
                    ? 'bg-white dark:bg-slate-900 border-sky-500 text-sky-400'
                    : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-600'
                }`}
              >
                {done ? <Check size={14} /> : idx + 1}
              </div>
              <span
                className={`mt-1.5 text-[11px] font-medium whitespace-nowrap ${
                  active ? 'text-sky-400' : done ? 'text-slate-600 dark:text-slate-300' : 'text-slate-600'
                }`}
              >
                {step.label}
              </span>
            </div>

            {/* Connector */}
            {idx < steps.length - 1 && (
              <div
                className={`flex-1 h-0.5 mx-2 mb-5 transition-all ${
                  idx < current ? 'bg-sky-600' : 'bg-slate-100 dark:bg-slate-800'
                }`}
              />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

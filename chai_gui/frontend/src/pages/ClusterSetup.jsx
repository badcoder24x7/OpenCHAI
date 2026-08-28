/**
 * ClusterSetup.jsx — Cluster Setup Wizard v4
 *
 * 6-step guided wizard driven by cluster_setup/ directory structure.
 *
 * Step 1  Setup Type     — discovered from CLUSTER_SETUP_DIR (ha / single)
 * Step 2  Node Role      — sub-directories inside the chosen type dir
 * Step 3  Task Selection — all *.yml files inside selected role dirs
 * Step 4  Variables      — vars extracted live from selected playbooks only
 * Step 5  Target Nodes   — --limit from inventory_def.txt or manual input
 * Step 6  Review & Run   — dry-run toggle, verbosity, live WebSocket console
 *
 * API contract (all via clusterSetupApi from api.js):
 *   types()                               GET /cluster-setup/types
 *   roles(setupType)                      GET /cluster-setup/{type}/roles
 *   playbooks(setupType, roleId)          GET /cluster-setup/{type}/{role}/playbooks
 *   multiPlaybookVars(type, role, paths)  GET /cluster-setup/{type}/{role}/multi-playbook-vars
 *   nodes()                               GET /cluster-setup/nodes
 *   validate(vars)                        POST /cluster-setup/validate
 *   run(data)                             POST /cluster-setup/run
 */

import React, { useState, useEffect, useRef, useCallback } from 'react'
import toast from 'react-hot-toast'
import yamlLib from 'js-yaml'
import { clusterSetupApi, createLogSocket } from '../api/api.js'
import Stepper from '../components/Stepper.jsx'
import {
  Server, Layers, ChevronRight, ChevronLeft, Play, Zap,
  CheckCircle2, XCircle, AlertCircle, Loader2, BookOpen,
  Terminal, Eye, EyeOff, Trash2, Download, Pause, Search,
  Users, Network, Info, Filter, StopCircle, Settings,
} from 'lucide-react'

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

const WIZARD_STEPS = [
  { label: 'Setup Type'   },
  { label: 'Node Role'    },
  { label: 'Select Tasks' },
  { label: 'Variables'    },
  { label: 'Target Nodes' },
  { label: 'Review & Run' },
]

const ROLE_ICONS = {
  headnode:       <Server  size={16} className="text-sky-400"    />,
  hpc_master:     <Layers  size={16} className="text-purple-400" />,
  hpc_management: <Network size={16} className="text-teal-400"   />,
  hpc_login:      <Users   size={16} className="text-green-400"  />,
  bmcnode:        <Server  size={16} className="text-orange-400" />,
  single_server:  <Server  size={16} className="text-sky-400"    />,
}

function logColor(line) {
  if (/✅.*SUCCESS|✅.*completed/i.test(line)) return 'text-green-300 font-semibold'
  if (/❌.*FAILED|❌.*completed/i.test(line))  return 'text-red-400 font-semibold'
  if (/⏹.*cancelled/i.test(line))             return 'text-yellow-400 font-semibold'
  if (/FAILED|ERROR|fatal/i.test(line))        return 'text-red-400'
  if (/SUCCESS|✅/i.test(line))                return 'text-green-300 font-semibold'
  if (/\bok=\d/i.test(line))                   return 'text-green-400'
  if (/changed=\d/i.test(line))               return 'text-yellow-300'
  if (/PLAY \[|TASK \[/i.test(line))           return 'text-sky-300 font-semibold'
  if (/skipping/i.test(line))                 return 'text-slate-500 dark:text-slate-400'
  if (/warning/i.test(line))                  return 'text-orange-400'
  if (/STDERR/i.test(line))                   return 'text-red-500'
  if (/^[-=]{3,}/.test(line))                 return 'text-slate-700'
  return 'text-slate-600 dark:text-slate-300'
}

function Spinner() {
  return (
    <div className="flex justify-center py-16">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 — Setup Type
// ─────────────────────────────────────────────────────────────────────────────
function StepSetupType({ types, selected, onSelect, csDir, dirExists }) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">Select Deployment Type</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Auto-discovered from{' '}
          <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-sky-400 font-mono text-[11px]">
            {csDir || '$OPENCHAI_ROOT/cluster_setup'}
          </code>
        </p>
      </div>

      {!dirExists && (
        <div className="flex items-start gap-3 p-4 bg-yellow-900/20 border border-yellow-700/40 rounded-xl text-sm">
          <AlertCircle size={15} className="text-yellow-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-yellow-300 font-medium">cluster_setup directory not found</p>
            <p className="text-yellow-600 text-xs mt-1">
              Create <code className="bg-yellow-900/30 px-1 rounded">cluster_setup/</code> under{' '}
              <code className="bg-yellow-900/30 px-1 rounded">OPENCHAI_ROOT</code> with{' '}
              <code className="bg-yellow-900/30 px-1 rounded">ha_server_setup/</code> and{' '}
              <code className="bg-yellow-900/30 px-1 rounded">single_server/</code> sub-directories.
            </p>
          </div>
        </div>
      )}

      {types.length === 0 && dirExists && (
        <div className="flex items-center gap-3 p-4 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl text-sm text-slate-600 dark:text-slate-400">
          <Info size={15} className="shrink-0" />
          No setup type directories found inside cluster_setup/.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {types.map((t) => {
          const active = selected === t.id
          return (
            <button
              key={t.id}
              onClick={() => onSelect(t.id)}
              className={`p-5 rounded-xl border-2 text-left transition-all ${
                active
                  ? 'border-sky-500 bg-sky-900/20 shadow-lg shadow-sky-900/10'
                  : 'border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800/80'
              }`}
            >
              <div className="flex items-center gap-3 mb-2">
                {t.id === 'ha'
                  ? <Layers size={20} className={active ? 'text-sky-400' : 'text-slate-500 dark:text-slate-400'} />
                  : <Server  size={20} className={active ? 'text-sky-400' : 'text-slate-500 dark:text-slate-400'} />}
                <span className={`font-semibold text-sm ${active ? 'text-sky-300' : 'text-slate-800 dark:text-slate-200'}`}>
                  {t.label}
                </span>
                {active && <CheckCircle2 size={14} className="text-sky-400 ml-auto" />}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">{t.description}</p>
              <p className="text-[10px] font-mono text-slate-700">dir: {t.dir_name}/</p>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 2 — Node Role Selection
// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// STEP 2 — Node Role Selection
// ─────────────────────────────────────────────────────────────────────────────
function StepRoleSelect({
  roles,
  selectedRoles,
  onToggle,
  setupType,
}) {

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">

        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">
            Select Node Role
          </h2>

          <p className="text-xs text-slate-500 dark:text-slate-400">
            Each role maps to a directory of playbooks inside{' '}
            <span className="text-sky-400 font-mono">
              {setupType}/
            </span>
          </p>
        </div>

      </div>

      {/* Empty State */}
      {roles.length === 0 ? (

        <div className="card flex flex-col items-center py-12 text-slate-600">

          <BookOpen
            size={30}
            className="mb-2 opacity-30"
          />

          <p className="text-sm">
            No node roles found for this setup type.
          </p>

          <p className="text-xs mt-1">
            Check your cluster_setup/ directory structure.
          </p>

        </div>

      ) : (

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">

          {roles.map((role) => {

            //
            // Single selection logic
            //
            const checked =
              selectedRoles.length > 0 &&
              selectedRoles[0] === role.id

            return (

              <label
                key={role.id}
                className={`flex items-start gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all ${
                  checked
                    ? 'border-sky-600/60 bg-sky-900/10'
                    : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-600'
                }`}
              >

                {/* Radio Input */}
                <input
                  type="radio"
                  name="node-role-selection"
                  checked={checked}
                  onChange={() => onToggle([role.id])}
                  className="mt-0.5 w-4 h-4 accent-sky-500 shrink-0"
                />

                {/* Content */}
                <div className="flex-1 min-w-0">

                  <div className="flex items-center gap-2 mb-1">

                    {ROLE_ICONS[role.id] || (
                      <Server
                        size={14}
                        className="text-slate-600 dark:text-slate-400"
                      />
                    )}

                    <span
                      className={`text-sm font-semibold ${
                        checked
                          ? 'text-sky-300'
                          : 'text-slate-800 dark:text-slate-200'
                      }`}
                    >
                      {role.label}
                    </span>

                  </div>

                  {role.description && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">
                      {role.description}
                    </p>
                  )}

                  <p className="text-[10px] font-mono text-slate-700">
                    {role.playbook_count} playbook
                    {role.playbook_count !== 1 ? 's' : ''} · {role.id}/
                  </p>

                </div>

              </label>
            )
          })}

        </div>
      )}

    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 — Task / Playbook Selection
// ─────────────────────────────────────────────────────────────────────────────
function StepTaskSelect({ rolePlaybooks, selectedTasks, onToggle }) {
  const totalSelected = Object.values(selectedTasks).flat().length

  const toggleRole = (roleId, checked) => {
    const pbs = rolePlaybooks[roleId]?.playbooks || []
    pbs.forEach((pb) => onToggle(roleId, pb.full_path, checked))
  }

  const [showAdvanced, setShowAdvanced] = useState(false)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">Select Tasks to Execute</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {totalSelected} task{totalSelected !== 1 ? 's' : ''} selected.
            Variables are derived from selected playbooks in the next step.
          </p>
        </div>
        <button
          onClick={() => setShowAdvanced((s) => !s)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
            showAdvanced
              ? 'bg-amber-900/20 border-amber-700/40 text-amber-300'
              : 'bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:text-slate-200'
          }`}
        >
          <Settings size={12}/>
          Advanced {showAdvanced ? '(hide optional)' : '(show optional)'}
        </button>
      </div>

      {Object.entries(rolePlaybooks).map(([roleId, { role, playbooks }]) => {
        const mandatory = playbooks.filter((p) => !p.optional)
        const optional  = playbooks.filter((p) => p.optional)
        const visible   = showAdvanced ? playbooks : mandatory
        const selected  = selectedTasks[roleId] || []
        const allChecked  = visible.length > 0 && visible.every((p) => selected.includes(p.full_path))
        const someChecked = visible.some((p) => selected.includes(p.full_path))

        return (
          <div
            key={roleId}
            className={`rounded-xl border transition-all ${
              someChecked ? 'border-sky-700/40 bg-sky-900/5' : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50'
            }`}
          >
            <div className="flex items-center gap-3 p-4">
              <input
                type="checkbox"
                checked={allChecked}
                ref={(el) => { if (el) el.indeterminate = someChecked && !allChecked }}
                onChange={(e) => toggleRole(roleId, e.target.checked)}
                className="w-4 h-4 accent-sky-500 shrink-0"
              />
              <div className="flex items-center gap-2 flex-1">
                {ROLE_ICONS[roleId] || <Server size={14} className="text-slate-600 dark:text-slate-400" />}
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{role?.label || roleId}</span>
                <span className="text-[10px] text-slate-600">
                  ({mandatory.length} mandatory{optional.length > 0 ? `, ${optional.length} optional` : ''})
                </span>
              </div>
            </div>

            {visible.length > 0 ? (
              <div className="border-t border-slate-200 dark:border-slate-800/60 px-4 pb-3 pt-1 space-y-0.5">
                {/* Mandatory playbooks */}
                {mandatory.map((pb) => (
                  <label
                    key={pb.full_path}
                    className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800/40 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={(selectedTasks[roleId] || []).includes(pb.full_path)}
                      onChange={(e) => onToggle(roleId, pb.full_path, e.target.checked)}
                      className="w-3.5 h-3.5 accent-sky-500 shrink-0"
                    />
                    <BookOpen size={11} className="text-slate-600 shrink-0" />
                    <span className="text-xs font-mono text-slate-600 dark:text-slate-300 truncate">{pb.name}</span>
                  </label>
                ))}
                {/* Optional playbooks — only visible when Advanced is on */}
                {showAdvanced && optional.length > 0 && (
                  <>
                    <div className="flex items-center gap-2 mt-2 mb-1">
                      <div className="h-px flex-1 bg-amber-700/30"/>
                      <span className="text-[10px] text-amber-500/70 uppercase tracking-wide">Optional</span>
                      <div className="h-px flex-1 bg-amber-700/30"/>
                    </div>
                    {optional.map((pb) => (
                      <label
                        key={pb.full_path}
                        className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-amber-900/10 cursor-pointer border border-dashed border-amber-800/30"
                      >
                        <input
                          type="checkbox"
                          checked={(selectedTasks[roleId] || []).includes(pb.full_path)}
                          onChange={(e) => onToggle(roleId, pb.full_path, e.target.checked)}
                          className="w-3.5 h-3.5 accent-amber-500 shrink-0"
                        />
                        <BookOpen size={11} className="text-amber-700 shrink-0" />
                        <span className="text-xs font-mono text-amber-400/80 truncate">{pb.name}</span>
                        <span className="text-[9px] text-amber-600 ml-auto shrink-0">optional</span>
                      </label>
                    ))}
                  </>
                )}
              </div>
            ) : (
              <p className="px-4 pb-3 text-xs text-slate-600 italic">No playbooks in this role directory.</p>
            )}
          </div>
        )
      })}

      {Object.keys(rolePlaybooks).length === 0 && (
        <div className="card flex flex-col items-center py-12 text-slate-600">
          <BookOpen size={30} className="mb-2 opacity-30" />
          <p className="text-sm">No roles loaded. Go back and select node roles.</p>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 4 — Variable Input
// ─────────────────────────────────────────────────────────────────────────────
// Standardised dropdown options for known Ansible variables.
// Replaces free-text inputs to prevent syntax errors during orchestration.
// ─────────────────────────────────────────────────────────────────────────────
const KNOWN_ENUM_FIELDS = {
  // phase1.0_firewall.yml — firewall service state
  fw_service_state:     ['started', 'stopped', 'restarted'],
  firewall_state:       ['started', 'stopped', 'restarted'],
  fw_state:             ['started', 'stopped', 'restarted'],
  // phase1.1_selinux.yml — SELinux enforcement mode
  selinux_mode:         ['enforcing', 'permissive', 'disabled'],
  selinux_state:        ['enforcing', 'permissive', 'disabled'],
  se_mode:              ['enforcing', 'permissive', 'disabled'],
}

function VarField({ field, value, onChange }) {
  const [show, setShow] = useState(false)

  // ── Standardised enum dropdown (firewall state, selinux mode, etc.) ───────
  const enumOptions = KNOWN_ENUM_FIELDS[field.name?.toLowerCase()]
  if (enumOptions) return (
    <select
      className="input text-xs"
      value={value ?? field.default ?? enumOptions[0]}
      onChange={(e) => onChange(e.target.value)}
    >
      {enumOptions.map((opt) => (
        <option key={opt} value={opt}>{opt}</option>
      ))}
    </select>
  )

  // ── YAML / structured type (dict, list-of-dicts like nfs_exports) ─────────
  // Rendered as a monospace textarea so the user can read and edit the
  // YAML structure directly. Validation is skipped for this type so that
  // structured values never trigger the "should be numeric" error.
  if (field.type === 'yaml') return (
    <div className="col-span-2">
      <textarea
        className="input text-xs font-mono w-full resize-y leading-5"
        rows={Math.min(12, (value ?? field.default ?? '').split('\n').length + 2)}
        value={value ?? field.default ?? ''}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        placeholder="# YAML value"
      />
      <p className="text-[10px] text-slate-600 mt-1">
        Structured value — edit as YAML. Parsed back into a proper JSON object/array before running.
      </p>
    </div>
  )

  if (field.type === 'list') return (
    <input
      className="input text-xs"
      value={value ?? field.default ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder="comma-separated values"
    />
  )

  if (field.type === 'boolean') return (
    <select
      className="input text-xs"
      value={String(value ?? field.default)}
      onChange={(e) => onChange(e.target.value === 'true')}
    >
      <option value="true">true</option>
      <option value="false">false</option>
    </select>
  )

  if (field.type === 'number') return (
    <input
      type="number"
      className="input text-xs"
      value={value ?? field.default ?? ''}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  )

  if (field.type === 'password') return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        className="input text-xs pr-9"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="••••••"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute right-2 top-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-300"
      >
        {show ? <EyeOff size={13} /> : <Eye size={13} />}
      </button>
    </div>
  )

  return (
    <input
      type="text"
      className="input text-xs"
      value={value ?? field.default ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={String(field.default ?? '')}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Fix 10: Per-playbook variable wizard — each playbook gets its own sub-page
// with Previous / Next navigation so the user configures one playbook at a time
// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// Reconstruct native types for submission
// ─────────────────────────────────────────────────────────────────────────────
// The variable editor stores every value as a plain string/number/boolean
// (whatever the input element produces) for easy editing — "yaml"-type
// fields are edited as YAML text, "list"-type fields as a comma-separated
// string. Ansible needs the ACTUAL native type (a real JSON object/array),
// not its text representation, or --extra-vars receives the literal string
// "nameservers:\n- 10.0.0.1" instead of a parsed object. This reconstructs
// the correct native value for every variable, driven by each field's
// `type` (from the backend's playbook parser) — not by a hardcoded list of
// variable names — so it works for any current or future playbook without
// GUI changes.
function reconstructTypedVars(rawVars, playbookVarsData) {
  const nameToType = {}
  for (const pb of playbookVarsData || []) {
    for (const field of pb.form_fields || []) {
      nameToType[field.name] = field.type
    }
  }

  const out = {}
  for (const [key, value] of Object.entries(rawVars)) {
    const type = nameToType[key]

    if (type === 'yaml' && typeof value === 'string') {
      try {
        const parsed = yamlLib.load(value)
        out[key] = (parsed && typeof parsed === 'object') ? parsed : value
      } catch {
        // Malformed YAML — send the raw string through rather than
        // silently dropping the variable; validation/Ansible will surface
        // the error clearly instead of this failing invisibly here.
        out[key] = value
      }
      continue
    }

    if (type === 'list' && typeof value === 'string') {
      out[key] = value.split(',').map((s) => s.trim()).filter(Boolean)
      continue
    }

    out[key] = value
  }
  return out
}

function StepVariables({ playbookVarsData, varValues, onVarChange, onValidate, validation, validating }) {
  // Only show playbooks that actually have fields
  const pagesData = playbookVarsData.filter((p) => p.form_fields?.length > 0)
  const [pbIdx, setPbIdx]     = useState(0)
  const [search, setSearch]   = useState('')
  const hasFields = pagesData.length > 0
  const currentPb = pagesData[pbIdx] || null
  const total     = pagesData.length

  // Reset to first page whenever the playbook list changes
  useEffect(() => { setPbIdx(0) }, [playbookVarsData])

  const goNext = () => { if (pbIdx < total - 1) { setPbIdx(pbIdx + 1); setSearch('') } }
  const goPrev = () => { if (pbIdx > 0)         { setPbIdx(pbIdx - 1); setSearch('') } }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">Configure Variables</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Configure variables for each playbook one at a time.
            Use <strong>Previous</strong> / <strong>Next</strong> to navigate between playbooks.
          </p>
        </div>
        <button onClick={onValidate} disabled={validating} className="btn-secondary text-xs">
          {validating ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
          Validate All
        </button>
      </div>

      {validation && (
        <div className={`p-3 rounded-lg border text-xs ${
          validation.valid ? 'bg-green-900/20 border-green-700/50' : 'bg-red-900/20 border-red-700/50'
        }`}>
          <div className="flex items-center gap-2 font-semibold mb-1">
            {validation.valid
              ? <CheckCircle2 size={12} className="text-green-400" />
              : <XCircle      size={12} className="text-red-400"   />}
            {validation.valid ? 'All variables valid' : `${validation.errors.length} error(s)`}
          </div>
          {validation.errors.map((e, i)   => <p key={i} className="text-red-300 pl-4">• {e}</p>)}
          {validation.warnings.map((w, i) => <p key={i} className="text-yellow-400 pl-4">⚠ {w}</p>)}
        </div>
      )}

      {!hasFields && (
        <div className="flex items-center gap-3 p-4 bg-slate-100 dark:bg-slate-800/50 border border-slate-300 dark:border-slate-700 rounded-xl text-sm text-slate-600 dark:text-slate-400">
          <Info size={15} className="shrink-0" />
          No configurable variables found in the selected playbooks. Proceed to the next step.
        </div>
      )}

      {hasFields && currentPb && (
        <>
          {/* Progress bar + playbook breadcrumb */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>Playbook {pbIdx + 1} of {total}</span>
              <span className="font-medium text-slate-600 dark:text-slate-400">{currentPb.name}</span>
            </div>
            <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-1.5">
              <div
                className="bg-sky-500 h-1.5 rounded-full transition-all"
                style={{ width: `${((pbIdx + 1) / total) * 100}%` }}
              />
            </div>
            {/* Playbook dots navigation */}
            {total > 1 && (
              <div className="flex items-center gap-1.5 justify-center flex-wrap pt-1">
                {pagesData.map((pb, i) => (
                  <button
                    key={pb.full_path}
                    onClick={() => { setPbIdx(i); setSearch('') }}
                    title={pb.file}
                    className={`h-2 rounded-full transition-all ${
                      i === pbIdx
                        ? 'w-6 bg-sky-500'
                        : 'w-2 bg-slate-600 hover:bg-slate-500'
                    }`}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Variable card for current playbook */}
          <div className="card space-y-3">
            <div className="flex items-center gap-2 pb-3 border-b border-slate-200 dark:border-slate-800">
              <BookOpen size={12} className="text-sky-400" />
              <p className="text-xs font-mono font-semibold text-slate-800 dark:text-slate-200">{currentPb.file}</p>
              <span className="ml-auto text-[10px] text-slate-600">
                {currentPb.form_fields.length} variable{currentPb.form_fields.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Search within this playbook's vars */}
            <div className="relative max-w-sm">
              <Search size={12} className="absolute left-3 top-2.5 text-slate-500 dark:text-slate-400" />
              <input
                className="input pl-9 text-xs"
                placeholder="Search variables…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {currentPb.form_fields
                .filter((f) => {
                  const q = search.trim().toLowerCase().replace(/[\s_-]+/g, ' ').trim()
                  if (!q) return true
                  // search_text (from the backend) already covers the field's
                  // own name plus every key nested inside it at any depth
                  // (dicts, lists, lists of dicts) and is formatting-normalized.
                  // Fall back to a plain name match for any older cached
                  // response that predates search_text.
                  const haystack = f.search_text || f.name.toLowerCase().replace(/[\s_-]+/g, ' ')
                  return haystack.includes(q)
                })
                .map((field) => (
                  <div key={field.name} className={field.type === 'yaml' ? 'md:col-span-2' : ''}>
                    <label className="label">{field.label}</label>
                    <VarField
                      field={field}
                      value={varValues[currentPb.full_path]?.[field.name]}
                      onChange={(v) => onVarChange(currentPb.full_path, field.name, v)}
                    />
                  </div>
                ))}
            </div>
          </div>

          {/* Previous / Next navigation */}
          <div className="flex items-center justify-between pt-1">
            <button
              onClick={goPrev}
              disabled={pbIdx === 0}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <span className="text-xs text-slate-600">
              {pbIdx + 1} / {total}
            </span>
            <button
              onClick={goNext}
              disabled={pbIdx === total - 1}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-sky-700 text-white hover:bg-sky-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 5 — Target Nodes
// ─────────────────────────────────────────────────────────────────────────────
function StepTargetNodes({ nodes, groups, selectedNodes, onToggle, limit, setLimit, selectedRoles }) {
  const [filter, setFilter] = useState('')
  const [showAll, setShowAll] = useState(false)

  // Context-aware filtering: show only nodes whose group matches the selected role.
  // This prevents confusion from unrelated nodes cluttering the target list.
  // The user can toggle "Show all nodes" to override.
  const roleGroupMap = {
    hpc_master:     'hpc_master',
    headnode:       'headnode',
    hpc_management: 'mgmt',
    hpc_login:      'login',
    bmcnode:        'bmc',
    compute:        'compute',
  }
  const selectedRole = selectedRoles?.[0] || ''
  const roleGroup    = roleGroupMap[selectedRole] || selectedRole

  const contextNodes = (!showAll && roleGroup)
    ? nodes.filter((n) => n.group?.toLowerCase() === roleGroup.toLowerCase())
    : nodes

  const displayNodes = contextNodes.filter(
    (n) => !filter ||
      n.ansible_hostname?.includes(filter) ||
      n.ip?.includes(filter) ||
      n.group?.includes(filter)
  )

  const visible = displayNodes
  const allChecked = contextNodes.length > 0 && contextNodes.every((n) => selectedNodes.includes(n.ansible_hostname))

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">Target Nodes</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Select target nodes — maps to Ansible's{' '}
          <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">--limit</code>.
          Leave blank to run on all inventory hosts.
        </p>
      </div>

      {/* Context-aware filter notice */}
      {selectedRole && !showAll && (
        <div className="flex items-center justify-between p-3 bg-sky-900/20 border border-sky-700/40 rounded-lg text-xs">
          <div className="flex items-center gap-2 text-sky-300">
            <Filter size={12}/>
            Showing only <strong>{roleGroup}</strong> nodes for role <strong>{selectedRole}</strong>
            {contextNodes.length === 0 && (
              <span className="text-yellow-400 ml-1">— no matching nodes found</span>
            )}
          </div>
          <button
            onClick={() => setShowAll(true)}
            className="text-sky-400 hover:text-sky-200 underline ml-3 shrink-0"
          >
            Show all nodes
          </button>
        </div>
      )}
      {showAll && (
        <div className="flex items-center justify-between p-2 bg-slate-100 dark:bg-slate-800 rounded-lg text-xs text-slate-600 dark:text-slate-400">
          <span>Showing all {nodes.length} inventory nodes</span>
          <button
            onClick={() => setShowAll(false)}
            className="text-sky-400 hover:text-sky-200 underline ml-3"
          >
            Filter by role
          </button>
        </div>
      )}

      {/* Group quick-select */}
      {groups.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">Quick:</span>
          <button
            onClick={() => contextNodes.forEach((n) => onToggle(n.ansible_hostname, true))}
            className="badge-blue cursor-pointer hover:opacity-80 text-xs"
          >All</button>
          <button
            onClick={() => contextNodes.forEach((n) => onToggle(n.ansible_hostname, false))}
            className="badge-gray cursor-pointer hover:opacity-80 text-xs"
          >None</button>
          {groups.map((g) => (
            <button
              key={g}
              onClick={() => contextNodes.forEach((n) => onToggle(n.ansible_hostname, n.group === g))}
              className="badge-green cursor-pointer hover:opacity-80 text-xs capitalize"
            >{g}</button>
          ))}
        </div>
      )}

      {/* Manual limit */}
      <div className="card space-y-2">
        <label className="label">Manual --limit override</label>
        <input
          className="input max-w-sm"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
          placeholder="hpc_master, cn01,cn02 — blank = all"
        />
        <p className="text-[11px] text-slate-600">
          Overrides checkbox selection when filled.
        </p>
      </div>

      {/* Node table */}
      <div className="card p-0 overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-950">
          <input
            type="checkbox"
            checked={allChecked}
            onChange={(e) => contextNodes.forEach((n) => onToggle(n.ansible_hostname, e.target.checked))}
            className="w-3.5 h-3.5 accent-sky-500 shrink-0"
          />
          <input
            className="input flex-1 text-xs py-1"
            placeholder="Filter by hostname, IP, group…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <span className="text-[10px] text-slate-600 shrink-0">
            {selectedNodes.length}/{contextNodes.length}
          </span>
        </div>
        {contextNodes.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-slate-600">
            <Server size={26} className="mb-2 opacity-30" />
            <p className="text-xs">{nodes.length === 0 ? 'No nodes in inventory_def.txt. Add via Inventory page.' : 'No nodes match the selected role group.'}</p>
          </div>
        ) : (
          <div className="max-h-60 overflow-y-auto divide-y divide-slate-200 dark:divide-slate-800/40">
            {visible.map((n) => (
              <label
                key={n.ansible_hostname}
                className="flex items-center gap-3 px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-800/30 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedNodes.includes(n.ansible_hostname)}
                  onChange={(e) => onToggle(n.ansible_hostname, e.target.checked)}
                  className="w-3.5 h-3.5 accent-sky-500 shrink-0"
                />
                <span className="text-xs font-mono text-slate-600 dark:text-slate-300 w-32 truncate">{n.ansible_hostname}</span>
                <span className="text-xs font-mono text-slate-500 dark:text-slate-400 w-28">{n.ip}</span>
                <span className="badge-blue text-[10px] capitalize">{n.group}</span>
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// LIVE CONSOLE
// ─────────────────────────────────────────────────────────────────────────────
function LiveConsole({ jobs, onClear }) {
  const [lines, setLines]   = useState([])
  const [paused, setPaused] = useState(false)
  const bottomRef           = useRef(null)
  const pausedRef           = useRef(false)
  pausedRef.current         = paused

  // FIX 6: sockets must persist across re-renders and only close when a job
  // actually finishes, the console is cleared, or this component unmounts —
  // NOT every time the `jobs` array gets a new reference (e.g. the next
  // playbook in a multi-playbook run starting). The previous implementation
  // returned `() => newSockets.forEach(ws => ws.close())` from an effect
  // keyed on `[jobs]`; React runs that cleanup before every re-invocation of
  // the effect, so the moment a second job was pushed, the first job's
  // still-active socket was closed and never reopened — the console just
  // went silent mid-deployment. A ref-backed map keyed by job_id survives
  // re-renders, so "already subscribed" and "still connected" mean the
  // same thing again.
  const socketsRef = useRef(new Map())  // job_id -> WebSocket

  const closeSocket = (jobId) => {
    const ws = socketsRef.current.get(jobId)
    if (ws) { ws.close(); socketsRef.current.delete(jobId) }
  }

  useEffect(() => {
    if (!jobs?.length) return
    for (const job of jobs) {
      if (socketsRef.current.has(job.job_id)) continue   // already streaming

      const ws = createLogSocket(
        job.job_id,
        (line) => {
          if (pausedRef.current) return
          // __done__:<status> sentinel — show a status badge line, don't echo the raw sentinel
          if (line.startsWith('__done__:')) {
            const status = line.slice(9)   // "success" | "failed" | "cancelled"
            const badge  = status === 'success'
              ? `\n✅  Job completed: SUCCESS`
              : status === 'cancelled'
              ? `\n⏹  Job cancelled`
              : `\n❌  Job completed: FAILED`
            setLines((prev) => [...prev.slice(-5000), `[${job.playbook}] ${badge}`])
            closeSocket(job.job_id)   // job is finished — free the connection now
            return
          }
          setLines((prev) => [...prev.slice(-5000), `[${job.playbook}] ${line}`])
        },
        () => {}
      )
      socketsRef.current.set(job.job_id, ws)
    }
  }, [jobs])

  // Close every remaining open socket only on true unmount (leaving this
  // step/wizard) — not on every `jobs` update, per FIX 6 above.
  useEffect(() => {
    return () => {
      socketsRef.current.forEach((ws) => ws.close())
      socketsRef.current.clear()
    }
  }, [])

  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, paused])

  const download = () => {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = Object.assign(document.createElement('a'), {
      href: url, download: 'cluster-setup.log',
    })
    a.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col h-full bg-slate-100 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 shrink-0">
        <div className="flex items-center gap-2">
          <Terminal size={12} className="text-sky-400" />
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">Live Execution Console</span>
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs text-slate-500 dark:text-slate-400">{lines.length} lines</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setPaused((p) => !p)} className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" title={paused ? 'Resume' : 'Pause'}>
            {paused ? <Play size={12} /> : <Pause size={12} />}
          </button>
          <button
            onClick={() => {
              setLines([])
              socketsRef.current.forEach((ws) => ws.close())
              socketsRef.current.clear()
              onClear?.()
            }}
            className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" title="Clear"
          >
            <Trash2 size={12} />
          </button>
          <button onClick={download} className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" title="Download">
            <Download size={12} />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-5">
        {lines.length === 0
          ? <p className="text-slate-700 italic">Waiting for output…</p>
          : lines.map((line, i) => <div key={i} className={logColor(line)}>{line || '\u00a0'}</div>)
        }
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 6 — Review & Run
// ─────────────────────────────────────────────────────────────────────────────
function StepReview({
  setupType, selectedRoles, rolePlaybooks, selectedTasks,
  varValues, selectedNodes, limit,
  dryRun, setDryRun, verbosity, setVerbosity,
  onRun, onCancel, running, currentPlaybook, jobs, onClearJobs,
}) {
  // Deduplicate — same playbook can appear in multiple role selections
  const allPaths = [...new Set(Object.values(selectedTasks).flat())]
  const target   = limit || (selectedNodes.length > 0 ? selectedNodes.join(',') : '(all nodes)')

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">Review & Execute</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">Confirm your configuration before deploying.</p>
      </div>

      {/* Summary */}
      <div className="card text-xs space-y-0">
        {[
          ['Setup Type', setupType === 'ha' ? 'HA Server Setup' : 'Single Server Setup'],
          ['Roles',      selectedRoles.join(', ') || '—'],
          ['Tasks',      `${allPaths.length} playbook${allPaths.length !== 1 ? 's' : ''}`],
          ['Target',     target],
        ].map(([k, v]) => (
          <div key={k} className="flex justify-between py-2 border-b border-slate-200 dark:border-slate-800/60 last:border-0">
            <span className="text-slate-500 dark:text-slate-400">{k}</span>
            <span className="font-mono text-slate-800 dark:text-slate-200 text-right max-w-xs truncate">{v}</span>
          </div>
        ))}
      </div>

      {/* Execution plan */}
      {allPaths.length > 0 && (
        <div className="card max-h-48 overflow-y-auto">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">
            Execution Plan
          </p>
          <div className="space-y-2">
            {Object.entries(selectedTasks).map(([roleId, paths]) => {
              if (!paths.length) return null
              const pbs = rolePlaybooks[roleId]?.playbooks || []
              return (
                <div key={roleId}>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-500 mb-1">
                    {rolePlaybooks[roleId]?.role?.label || roleId}
                  </p>
                  {paths.map((p) => {
                    const pb = pbs.find((x) => x.full_path === p)
                    return (
                      <div key={p} className="flex items-center gap-2 pl-3 py-0.5">
                        <ChevronRight size={10} className="text-slate-600" />
                        <span className="text-xs font-mono text-slate-600 dark:text-slate-400">{pb?.name || p}</span>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Execution options */}
      <div className="card space-y-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Execution Options
        </p>
        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-slate-600 dark:text-slate-400">
            <button
              type="button"
              onClick={() => setDryRun((d) => !d)}
              className={`relative w-9 h-5 rounded-full transition-colors ${dryRun ? 'bg-yellow-600' : 'bg-slate-300 dark:bg-slate-700'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${dryRun ? 'translate-x-4' : ''}`} />
            </button>
            <Zap size={12} className={dryRun ? 'text-yellow-400' : 'text-slate-600'} />
            Dry Run (--check)
          </label>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400">Verbosity:</span>
            {[0, 1, 2, 3, 4].map((v) => (
              <button
                key={v}
                onClick={() => setVerbosity(v)}
                className={`w-8 h-6 text-xs rounded transition-colors ${
                  verbosity === v ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-700'
                }`}
              >
                {v === 0 ? 'off' : `${v}v`}
              </button>
            ))}
          </div>
        </div>

        {dryRun && (
          <p className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/50 rounded-lg px-3 py-2">
            ⚡ Dry run — Ansible simulates all tasks with <code>--check</code>. No changes applied.
          </p>
        )}
      </div>

      {/* Run / Cancel buttons */}
      <div className="flex gap-3">
        <button
          onClick={onRun}
          disabled={running || allPaths.length === 0}
          className={`flex-1 py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-colors ${
            running || allPaths.length === 0
              ? 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 cursor-not-allowed'
              : dryRun
              ? 'bg-yellow-600 hover:bg-yellow-500 text-white'
              : 'bg-sky-600 hover:bg-sky-500 text-white'
          }`}
        >
          {running
            ? <><Loader2 size={15} className="animate-spin" /> {currentPlaybook ? `Running: ${currentPlaybook}` : 'Running…'}</>
            : dryRun
            ? <><Zap size={15} /> Dry Run ({allPaths.length} tasks)</>
            : <><Play size={15} /> Deploy Cluster ({allPaths.length} tasks)</>
          }
        </button>
        {running && (
          <button
            onClick={onCancel}
            className="px-5 py-3 rounded-xl font-semibold text-sm flex items-center gap-2 bg-red-900/40 hover:bg-red-800/60 text-red-300 border border-red-700/40 transition-colors"
          >
            <StopCircle size={15} /> Cancel
          </button>
        )}
      </div>

      {allPaths.length === 0 && !running && (
        <p className="text-xs text-slate-600 text-center">← Go back to Step 3 and select at least one task.</p>
      )}

      {jobs.length > 0 && (
        <div className="h-[480px] mt-2">
          <LiveConsole jobs={jobs} onClear={onClearJobs} />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN WIZARD
// ─────────────────────────────────────────────────────────────────────────────
export default function ClusterSetup({ preType } = {}) {
  const [step, setStep]             = useState(0)

  // Step 1
  const [types, setTypes]           = useState([])
  const [csDir, setCsDir]           = useState('')
  const [dirExists, setDirExists]   = useState(false)
  const [setupType, setSetupType]   = useState(preType || '')

  // Step 2
  const [roles, setRoles]             = useState([])
  const [selectedRoles, setSelRoles]  = useState([])
  const [rolesLoading, setRolesLoad]  = useState(false)

  // Step 3
  const [rolePlaybooks, setRolePbs]   = useState({})  // { roleId: { role, playbooks[] } }
  const [selectedTasks, setSelTasks]  = useState({})  // { roleId: [full_path, …] }
  const [pbLoading, setPbLoading]     = useState(false)

  // Step 4
  const [pbVarsData, setPbVarsData]   = useState([])
  const [varValues, setVarValues]     = useState({})
  const [varsLoading, setVarsLoad]    = useState(false)
  const [validation, setValidation]   = useState(null)
  const [validating, setValidating]   = useState(false)

  // Step 5
  const [nodes, setNodes]             = useState([])
  const [groups, setGroups]           = useState([])
  const [selectedNodes, setSelNodes]  = useState([])
  const [limit, setLimit]             = useState('')

  // Step 6
  const [dryRun, setDryRun]           = useState(false)
  const [verbosity, setVerbosity]     = useState(0)
  const [running, setRunning]         = useState(false)
  const [jobs, setJobs]               = useState([])
  const [currentJobId, setCurrentJobId] = useState(null)    // job being run right now (for cancel)
  const [currentPlaybook, setCurrentPlaybook] = useState('') // playbook name shown in button
  const cancelledRef                  = useRef(false)        // set true when user clicks Cancel

  const [initLoading, setInitLoad]    = useState(true)

  // ── Initial load ───────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    async function init() {
      setInitLoad(true)
      try {
        const [typesRes, nodesRes] = await Promise.all([
          clusterSetupApi.types(),
          clusterSetupApi.nodes(),
        ])
        if (cancelled) return
        const tList = typesRes.types || []
        setTypes(tList)
        setCsDir(typesRes.cluster_setup_dir || '')
        setDirExists(typesRes.exists || false)
        setNodes(nodesRes.nodes || [])
        setGroups(nodesRes.groups || [])

        if (preType) {
          const match = tList.find((t) => t.id === preType)
          if (match) setSetupType(match.id)
        } else if (tList.length === 1) {
          setSetupType(tList[0].id)
        }
      } catch (e) {
        toast.error(e.message)
      } finally {
        if (!cancelled) setInitLoad(false)
      }
    }
    init()
    return () => { cancelled = true }
  }, [])

  // ── Load roles when setup type changes ────────────────────────────────────
  useEffect(() => {
    if (!setupType) return
    setRoles([]); setSelRoles([]); setRolePbs({}); setSelTasks({}); setPbVarsData([])
    setRolesLoad(true)
    clusterSetupApi.roles(setupType)
      .then((res) => setRoles(res.roles || []))
      .catch((e) => toast.error(e.message))
      .finally(() => setRolesLoad(false))
  }, [setupType])

  // ── Load playbooks when selected roles change ─────────────────────────────
  useEffect(() => {
    if (!selectedRoles.length) { setRolePbs({}); setSelTasks({}); return }
    setPbLoading(true)
    Promise.all(
      selectedRoles.map((roleId) =>
        clusterSetupApi.playbooks(setupType, roleId).then((res) => ({ roleId, res }))
      )
    )
      .then((results) => {
        const newPbs    = {}
        const newTasks  = { ...selectedTasks }
        for (const { roleId, res } of results) {
          const role = roles.find((r) => r.id === roleId)
          newPbs[roleId] = { role, playbooks: res.playbooks || [] }
          if (!newTasks[roleId])
            // Only pre-select mandatory playbooks; optional ones start unchecked
            newTasks[roleId] = (res.playbooks || []).filter((p) => !p.optional).map((p) => p.full_path)
        }
        for (const roleId of Object.keys(newTasks)) {
          if (!selectedRoles.includes(roleId)) delete newTasks[roleId]
        }
        setRolePbs(newPbs)
        setSelTasks(newTasks)
      })
      .catch((e) => toast.error(e.message))
      .finally(() => setPbLoading(false))
  }, [selectedRoles])

  // ── Load vars when entering step 4 ───────────────────────────────────────
  useEffect(() => {
    if (step !== 3) return
    const allPaths = [...new Set(Object.values(selectedTasks).flat())]
    if (!allPaths.length) { setPbVarsData([]); return }
    const firstRole = Object.keys(selectedTasks)[0]
    setVarsLoad(true)
    clusterSetupApi.multiPlaybookVars(setupType, firstRole, allPaths)
      .then((res) => {
        setPbVarsData(res.playbooks || [])
        setVarValues((prev) => {
          const next = { ...prev }
          for (const pb of res.playbooks || []) {
            if (!next[pb.full_path]) next[pb.full_path] = {}
            for (const field of pb.form_fields || []) {
              if (next[pb.full_path][field.name] === undefined && field.type !== 'password')
                next[pb.full_path][field.name] = field.default ?? ''
            }
          }
          return next
        })
      })
      .catch((e) => toast.error(e.message))
      .finally(() => setVarsLoad(false))
  }, [step])

  // ── Helpers ───────────────────────────────────────────────────────────────
  // Single role selection
  const toggleRole = useCallback((roles) => {
    setSelRoles(roles)
  }, [])
  const toggleTask = useCallback((roleId, fullPath, checked) => {
    setSelTasks((prev) => ({
      ...prev,
      [roleId]: checked
        ? [...(prev[roleId] || []), fullPath]
        : (prev[roleId] || []).filter((p) => p !== fullPath),
    }))
  }, [])

  const handleVarChange = useCallback((pbPath, varName, value) => {
    setVarValues((prev) => ({
      ...prev,
      [pbPath]: { ...(prev[pbPath] || {}), [varName]: value },
    }))
    setValidation(null)   // FIX 7: a previous "valid" result no longer applies once values change
  }, [])

  const handleValidate = async () => {
    const merged = Object.values(varValues).reduce((acc, vars) => ({ ...acc, ...vars }), {})
    const typed  = reconstructTypedVars(merged, pbVarsData)
    setValidating(true)
    try {
      setValidation(await clusterSetupApi.validate(typed))
    } catch (e) {
      toast.error(e.message)
    } finally {
      setValidating(false)
    }
  }

  const toggleNode = useCallback((hostname, checked) => {
    setSelNodes((prev) => checked ? [...prev, hostname] : prev.filter((n) => n !== hostname))
  }, [])

  const handleRun = async () => {
    // Deduplicate then sort numerically by filename (phase1.0 → phase1.1 → …)
    const seen = new Set()
    const allPaths = Object.values(selectedTasks)
      .flat()
      .filter((p) => { if (seen.has(p)) return false; seen.add(p); return true })
      .sort((a, b) => {
        const nameA = a.split('/').pop() || a
        const nameB = b.split('/').pop() || b
        return nameA.localeCompare(nameB, undefined, { numeric: true, sensitivity: 'base' })
      })

    if (!allPaths.length) { toast.error('Select at least one task.'); return }

    // Build extra_vars — reconstruct each variable's real native type (a
    // real JSON object/array, not its text representation) using each
    // field's type from the backend playbook parser. This is what lets
    // e.g. fallback_dns (a dict of lists) and required_packages (a plain
    // list) reach Ansible correctly, for any playbook, not just ones on a
    // hardcoded list of variable names.
    const rawVars = {}
    for (const vars of Object.values(varValues)) {
      for (const [k, v] of Object.entries(vars)) {
        if (v === '' || v === null || v === undefined) continue
        rawVars[k] = v
      }
    }
    const extraVars = reconstructTypedVars(rawVars, pbVarsData)

    const effectiveLimit = limit || (selectedNodes.length ? selectedNodes.join(',') : null)
    const basePayload = {
      setup_type: setupType,
      role_id:    selectedRoles[0] || '',
      extra_vars: Object.keys(extraVars).length ? extraVars : null,
      limit:      effectiveLimit,
      dry_run:    dryRun,
      verbosity,
    }

    setRunning(true)
    setJobs([])
    setCurrentPlaybook('')
    setCancelledRef(false)
    let halted = false

    for (let i = 0; i < allPaths.length; i++) {
      if (cancelledRef.current) { halted = true; break }
      const pbPath = allPaths[i]
      const pbName = pbPath.split('/').pop() || pbPath
      setCurrentPlaybook(`${pbName} (${i + 1}/${allPaths.length})`)
      try {
        const res = await clusterSetupApi.runSingle({
          ...basePayload,
          playbook_paths: [pbPath],
        })
        const job = res.jobs?.[0]
        if (!job) { toast.error(`No job returned for ${pbName}`); halted = true; break }

        // Push job immediately so LiveConsole opens WebSocket right away
        setCurrentJobId(job.job_id)
        setJobs((prev) => [...prev, { ...job, playbook: pbName }])

        // Wait for this job to reach terminal before starting the next one
        const finished = await waitForJobTerminal(job.job_id)
        setCurrentJobId(null)

        if (finished?.status === 'cancelled') {
          toast.info('Execution cancelled by user.')
          halted = true; break
        }
        if (finished?.status === 'failed' && !dryRun) {
          toast.error(`Halted: ${pbName} failed — see console.`)
          halted = true; break
        }
      } catch (e) {
        toast.error(`Error launching ${pbName}: ${e.message}`)
        halted = true; break
      }
    }

    if (!halted) toast.success(`All ${allPaths.length} playbook(s) completed.`)
    setRunning(false)
    setCurrentJobId(null)
    setCurrentPlaybook('')
  }

  // FIX 8: Cancel the currently running job
  const handleCancel = async () => {
    cancelledRef.current = true
    if (currentJobId) {
      try {
        await clusterSetupApi.cancelJob(currentJobId)
        toast.info('Cancellation requested…')
      } catch (e) {
        toast.error(`Cancel failed: ${e.message}`)
      }
    } else {
      setRunning(false)
    }
  }

  function setCancelledRef(val) { cancelledRef.current = val }

  async function waitForJobTerminal(jobId, pollMs = 1500) {
    while (true) {
      await new Promise((r) => setTimeout(r, pollMs))
      try {
        const job = await clusterSetupApi.jobStatus(jobId)
        if (job?.status && job.status !== 'running') return job
      } catch { /* keep polling on transient error */ }
    }
  }

  // ── Navigation guard ──────────────────────────────────────────────────────
  // FIX 7: the Variables step must not be skippable until validation has run
  // and passed — unless the selected playbooks have no configurable variables
  // at all, in which case there's nothing to validate.
  const stepVarsHasFields = pbVarsData.some((p) => p.form_fields?.length > 0)
  const canNext = [
    !!setupType,
    selectedRoles.length > 0,
    Object.values(selectedTasks).flat().length > 0,
    !stepVarsHasFields || validation?.valid === true,
    true,
    false,
  ][step]

  if (initLoading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
    </div>
  )

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div>
        <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100">Cluster Setup Wizard</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Guided HPC deployment ·{' '}
          <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded text-[11px]">
            {csDir || '$OPENCHAI_ROOT/cluster_setup'}
          </code>
        </p>
      </div>

      <Stepper steps={WIZARD_STEPS} current={step} />

      <div className="card min-h-96">
        {step === 0 && (
          <StepSetupType
            types={types} selected={setupType}
            onSelect={(id) => { setSetupType(id); setJobs([]) }}
            csDir={csDir} dirExists={dirExists}
          />
        )}
        {step === 1 && (
          rolesLoading ? <Spinner /> :
          <StepRoleSelect
            roles={roles} selectedRoles={selectedRoles}
            onToggle={toggleRole} setupType={setupType}
          />
        )}
        {step === 2 && (
          pbLoading ? <Spinner /> :
          <StepTaskSelect
            rolePlaybooks={rolePlaybooks}
            selectedTasks={selectedTasks}
            onToggle={toggleTask}
          />
        )}
        {step === 3 && (
          varsLoading ? <Spinner /> :
          <StepVariables
            playbookVarsData={pbVarsData} varValues={varValues}
            onVarChange={handleVarChange} onValidate={handleValidate}
            validation={validation} validating={validating}
          />
        )}
        {step === 4 && (
          <StepTargetNodes
            nodes={nodes} groups={groups}
            selectedNodes={selectedNodes} onToggle={toggleNode}
            limit={limit} setLimit={setLimit}
            selectedRoles={selectedRoles}
          />
        )}
        {step === 5 && (
          <StepReview
            setupType={setupType} selectedRoles={selectedRoles}
            rolePlaybooks={rolePlaybooks} selectedTasks={selectedTasks}
            varValues={varValues} selectedNodes={selectedNodes} limit={limit}
            dryRun={dryRun} setDryRun={setDryRun}
            verbosity={verbosity} setVerbosity={setVerbosity}
            onRun={handleRun} onCancel={handleCancel} running={running}
            currentPlaybook={currentPlaybook}
            jobs={jobs} onClearJobs={() => setJobs([])}
          />
        )}

        {/* Navigation */}
        <div className="flex justify-between items-center mt-8 pt-5 border-t border-slate-200 dark:border-slate-800">
          <button
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 0}
            className="btn-secondary disabled:opacity-40"
          >
            <ChevronLeft size={14} /> Back
          </button>
          {step === 3 && stepVarsHasFields && validation?.valid !== true && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              Run <strong>Validate All</strong> above and resolve any errors to continue.
            </p>
          )}
          {step < WIZARD_STEPS.length - 1 && (
            <button
              onClick={() => setStep((s) => s + 1)}
              disabled={!canNext}
              title={!canNext && step === 3 ? 'Validate variables before continuing' : undefined}
              className="btn-primary disabled:opacity-40"
            >
              Next <ChevronRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
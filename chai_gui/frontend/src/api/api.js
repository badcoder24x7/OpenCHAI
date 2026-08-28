/**
 * OpenCHAI GUI — API client  (v3)
 *
 * Changes vs v2
 * ─────────────
 * - auditApi added (AuditLog page used dynamic import workaround — now proper export)
 * - chaiReleaseApi added (ChaiReleaseWizard referenced it but it was never exported)
 * - createLogtailSocket added for LiveLogTail component
 * - WS URL correctly uses /api proxy path in dev and direct path in prod
 * - axios interceptor preserves HTTP status on errors for 404 handling
 * - All API methods have consistent error handling via the interceptor
 */

import axios from 'axios'

// ─────────────────────────────────────────────────────────────────────────────
// Base HTTP client
// ─────────────────────────────────────────────────────────────────────────────

export const BASE_URL = import.meta.env.VITE_API_BASE || '/api'

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status
    const url    = err?.config?.url || ''

    // FIX 1: a 401 anywhere (except the login call itself — that's just a
    // wrong-password error, not an expired session) means the session is
    // dead. Tell the rest of the app once, centrally, instead of leaving
    // every page to show its own inline "token invalid" message.
    //
    // Issue #5 fix: /chai-release/* proxies to an EXTERNAL HPC registry —
    // a 401 from there means the registry rejected a username/password,
    // not that this app's own session expired. That distinction matters:
    // without it, a wrong registry password in the CHAI Release Wizard
    // used to log the user out of the entire application. The wizard's
    // /auth endpoint itself no longer returns a raw 401 for this reason,
    // but this exclusion stays as a second line of defense so no future
    // registry-proxied endpoint can reintroduce the same bug.
    const isRegistryProxyCall = url.includes('/chai-release/')
    if (status === 401 && !url.includes('/auth/login') && !isRegistryProxyCall) {
      window.dispatchEvent(new CustomEvent('openchai:unauthorized'))
    }

    const detail = err?.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || d).join(', ')
      : detail || err?.response?.data?.message || err?.message || 'Unknown error'
    // Attach status so callers can check err.status
    const error = new Error(msg)
    error.status = status
    return Promise.reject(error)
  },
)

export default client

// ─────────────────────────────────────────────────────────────────────────────
// Auth token — stored in module scope (in-memory, not localStorage)
// Injected into every request via interceptor below.
// ─────────────────────────────────────────────────────────────────────────────

let _token = null

export function setAuthToken(token) {
  _token = token
  if (token) {
    client.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete client.defaults.headers.common['Authorization']
  }
}

export function getAuthToken() { return _token }


// ─────────────────────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────────────────────

export const authApi = {
  login:  (username, password) =>
    client.post('/auth/login', { username, password }).then((r) => r.data),
  logout: () =>
    client.post('/auth/logout').then((r) => r.data),
  me:     () =>
    client.get('/auth/me').then((r) => r.data),
  status: () =>
    client.get('/auth/status').then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Cluster
// ─────────────────────────────────────────────────────────────────────────────

export const clusterApi = {
  create:  (data) => client.post('/cluster/create', data).then((r) => r.data),
  get:     ()     => client.get('/cluster').then((r) => r.data),
  state:   ()     => client.get('/cluster/state').then((r) => r.data),
  preview: ()     => client.get('/cluster/preview').then((r) => r.data),
  reset:   ()     => client.delete('/cluster').then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Nodes
// ─────────────────────────────────────────────────────────────────────────────

export const nodesApi = {
  list:   ()         => client.get('/nodes').then((r) => r.data),
  add:    (data)     => client.post('/nodes/add', data).then((r) => r.data),
  update: (id, data) => client.put(`/nodes/${id}`, data).then((r) => r.data),
  remove: (id)       => client.delete(`/nodes/${id}`).then((r) => r.data),
  bulk:   (nodes)    => client.post('/nodes/bulk', nodes).then((r) => r.data),
  health: ()         => client.get('/nodes/health/').then((r) => r.data),
  nodeHealth: (id)   => client.get(`/nodes/health/${id}`).then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Inventory Def
// ─────────────────────────────────────────────────────────────────────────────

export const inventoryDefApi = {
  list:    ()                    => client.get('/inventory-def').then((r) => r.data),
  add:     (data, backup = true) => client.post('/inventory-def/add', data, { params: { backup } }).then((r) => r.data),
  update:  (hn, data, backup = true) => client.put(`/inventory-def/${hn}`, data, { params: { backup } }).then((r) => r.data),
  remove:  (hn, backup = true)   => client.delete(`/inventory-def/${hn}`, { params: { backup } }).then((r) => r.data),
  bulk:    (text, backup = true) => client.post('/inventory-def/bulk', { text, backup }).then((r) => r.data),
  raw:     ()                    => client.get('/inventory-def/raw').then((r) => r.data),
  sshTest: (data)                => client.post('/inventory-def/ssh-test', data).then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Deploy
// ─────────────────────────────────────────────────────────────────────────────

export const deployApi = {
  start:     (data) => client.post('/deploy/start', data).then((r) => r.data),
  generate:  ()     => client.post('/deploy/generate').then((r) => r.data),
  jobs:      ()     => client.get('/deploy/jobs').then((r) => r.data),
  jobStatus: (id)   => client.get(`/deploy/jobs/${id}`).then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Playbooks
// ─────────────────────────────────────────────────────────────────────────────

export const playbooksApi = {
  list:       ()           => client.get('/playbooks').then((r) => r.data),
  categories: ()           => client.get('/playbooks/categories').then((r) => r.data),
  category:   (cat)        => client.get(`/playbooks/categories/${cat}`).then((r) => r.data),
  detail:     (cat, name)  => client.get(`/playbooks/detail/${cat}/${name}`).then((r) => r.data),
  groups:     ()           => client.get('/playbooks/inventory-groups').then((r) => r.data),
  execute:    (data)       => client.post('/playbooks/execute', data).then((r) => r.data),
  tree:       ()           => client.get('/playbooks/tree').then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Backup
// ─────────────────────────────────────────────────────────────────────────────

export const backupApi = {
  list:    (filePath) => client.get('/backup/list', {
    params: filePath ? { file_path: filePath } : {},
  }).then((r) => r.data),
  restore: (path) => client.post('/backup/restore', { backup_path: path }).then((r) => r.data),
  delete:  (path) => client.delete('/backup/delete', { data: { backup_path: path } }).then((r) => r.data),
  read:    (path) => client.get('/backup/read', { params: { backup_path: path } }).then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Logs
// ─────────────────────────────────────────────────────────────────────────────

export const logsApi = {
  stream: (jobId, lines = 200) =>
    client.get(`/logs/stream/${jobId}`, { params: { lines } }).then((r) => r.data),
  jobs: () => client.get('/logs/jobs').then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Info
// ─────────────────────────────────────────────────────────────────────────────

export const infoApi = {
  paths:   () => client.get('/info/paths').then((r) => r.data),
  tree:    () => client.get('/info/tree').then((r) => r.data),
  ansible: () => client.get('/info/ansible').then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Audit  (was missing — AuditLog page used dynamic import workaround)
// ─────────────────────────────────────────────────────────────────────────────

export const auditApi = {
  list:  (limit = 100, action) =>
    client.get('/audit', { params: { limit, ...(action ? { action } : {}) } }).then((r) => r.data),
  clear: () => client.delete('/audit').then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────────────────────
/*

export const authApi = {
  login:  (username, password) =>
    client.post('/auth/login', { username, password }).then((r) => r.data),
  logout: () =>
    client.post('/auth/logout').then((r) => r.data),
  me:     () =>
    client.get('/auth/me').then((r) => r.data),
  status: () =>
    client.get('/auth/status').then((r) => r.data),
}
*/
// ─────────────────────────────────────────────────────────────────────────────
// Cluster Setup
// ─────────────────────────────────────────────────────────────────────────────

export const clusterSetupApi = {
  types:          ()       => client.get('/cluster-setup/types').then((r) => r.data),
  phases:         (type)   => client.get(`/cluster-setup/${type}/phases`).then((r) => r.data),

  // ── v4 Wizard — cluster_setup/ directory based ───────────────────────────
  roles:             (setupType)                => client.get(`/cluster-setup/${setupType}/roles`).then((r) => r.data),
  playbooks:         (setupType, roleId)        => client.get(`/cluster-setup/${setupType}/${roleId}/playbooks`).then((r) => r.data),
  multiPlaybookVars: (setupType, roleId, paths) => client.get(`/cluster-setup/${setupType}/${roleId}/multi-playbook-vars`, { params: { paths: paths.join(',') } }).then((r) => r.data),
  // ─────────────────────────────────────────────────────────────────────────
  loadVars:       ()       => client.get('/cluster-setup/vars/load').then((r) => r.data),
  allVars:        ()       => client.get('/cluster-setup/vars/all').then((r) => r.data),
  updateVars:     (data)   => client.post('/cluster-setup/vars/update', data).then((r) => r.data),
  addVar:         (data)   => client.post('/cluster-setup/vars/add-var', data).then((r) => r.data),
  deleteVar:      (data)   => client.delete('/cluster-setup/vars/delete-var', { data }).then((r) => r.data),
  run:            (data)   => client.post('/cluster-setup/run', data).then((r) => r.data),
  runSingle:      (data)   => client.post('/cluster-setup/run-single', data).then((r) => r.data),
  jobStatus:      (id)     => client.get(`/cluster-setup/jobs/${id}`).then((r) => r.data),
  cancelJob:      (id)     => client.post(`/cluster-setup/jobs/${id}/cancel`).then((r) => r.data),
  nodes:          ()       => client.get('/cluster-setup/nodes').then((r) => r.data),
  validate:       (vars)   => client.post('/cluster-setup/validate', { variables: vars }).then((r) => r.data),
  templates:      ()       => client.get('/cluster-setup/templates').then((r) => r.data),
  saveTemplate:   (data)   => client.post('/cluster-setup/templates/save', data).then((r) => r.data),
  loadTemplate:   (name)   => client.post(`/cluster-setup/templates/load/${name}`).then((r) => r.data),
  deleteTemplate: (name)   => client.delete(`/cluster-setup/templates/${name}`).then((r) => r.data),
}

// ─────────────────────────────────────────────────────────────────────────────
// CHAI Release  (was missing — ChaiReleaseWizard referenced it but never exported)
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Wizard section info — Markdown help content shown in the CHAI Release
// wizard's per-step info sidebar.
// ─────────────────────────────────────────────────────────────────────────────
export const wizardInfoApi = {
  all: () => client.get('/wizard-info/all').then((r) => r.data),
}

export const chaiReleaseApi = {
  // ── System ────────────────────────────────────────────────────────────────
  systemInfo: () => client.get('/chai-release/system-info').then((r) => r.data),

  // ── Registry listings (verify_ssl=null → backend uses CHAI_VERIFY_SSL env var) ──
  architectures: (verify_ssl = null) =>
    client.get('/chai-release/architectures', { params: { verify_ssl } }).then((r) => r.data),

  distributions: (arch, verify_ssl = null) =>
    client.get(`/chai-release/distributions/${arch}`, { params: { verify_ssl } }).then((r) => r.data),

  // ── Local-only listings (no registry call — used by the skip-auth path) ──
  localArchitectures: () =>
    client.get('/chai-release/local-architectures').then((r) => r.data),

  localDistributions: (arch) =>
    client.get(`/chai-release/local-distributions/${arch}`).then((r) => r.data),

  // ── Versions ──────────────────────────────────────────────────────────────
  versions: (
    arch,
    os_dist,
    verify_ssl = null,
  ) =>
    client
      .get(
        `/chai-release/versions/${arch}/${os_dist}`,
        {
          params: { verify_ssl },
        },
      )
      .then((r) => r.data),

  // ── Releases ──────────────────────────────────────────────────────────────
  // Version-independent local release notes — used by the Release step that
  // now appears BEFORE the Version step in the wizard.
  releaseNotes: () =>
    client.get('/chai-release/release-notes').then((r) => r.data),

  releases: (
    arch,
    os_dist,
    openchai_version,
    verify_ssl = null,
  ) =>
    client
      .get(
        `/chai-release/releases/${arch}/${os_dist}/${openchai_version}`,
        {
          params: { verify_ssl },
        },
      )
      .then((r) => r.data),

  releaseContent: (
    path,
    assetType,
    verify_ssl = null,
  ) =>
    client.get('/chai-release/release-content', {
      params: {
        path,
        asset_type: assetType,
        verify_ssl,
      },
      responseType: 'text',
     }).then((r) => r.data),	
  // ── Cluster Configuration tab — local install check ──────────────────────
  localInstallStatus: () =>
    client.get('/chai-release/local-install-status').then((r) => r.data),

  // ── Execute ───────────────────────────────────────────────────────────────
  execute: (data) => client.post('/chai-release/execute', data).then((r) => r.data),

  // ── Container images (Step 5 — mirrors container_img_selector.py) ─────────
  containerTools: () =>
    client.get('/chai-release/container-tools').then((r) => r.data),

  containerVersions: (tool, os_dist, verify_ssl = null) =>
    client.get(`/chai-release/container-versions/${tool}/${os_dist}`, {
      params: { verify_ssl },
    }).then((r) => r.data),

  containerImages: (tool, os_dist, version, verify_ssl = null) =>
    client.get(`/chai-release/container-images/${tool}/${os_dist}/${version}`, {
      params: { verify_ssl },
    }).then((r) => r.data),

  containerExecute: (data) =>
    client.post('/chai-release/container-execute', data).then((r) => r.data),

  // ── Jobs ──────────────────────────────────────────────────────────────────
  jobs:      ()  => client.get('/chai-release/jobs').then((r) => r.data),
  jobStatus: (id) => client.get(`/chai-release/jobs/${id}`).then((r) => r.data),

  // ── Auth (client-side cache + server-side persistence) ────────────────────
  _auth: { type: 'none', username: '', password: '', token: '' },
  setAuth(auth) { this._auth = { ...auth } },
  getAuth()     { return this._auth },

  /**
   * POST credentials to backend BEFORE any listing call.
   * The backend _resolve_auth() reads from the server-side store for all
   * subsequent GET requests. Must be awaited in handleSaveAuth().
   */
  persistAuth(auth) {
    return client.post('/chai-release/auth', {
      auth_type: auth.type     || 'none',
      username:  auth.username || null,
      password:  auth.password || null,
      token:     auth.token    || null,
    }).then((r) => r.data)
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket factory — Ansible job log streaming
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Creates a WebSocket that streams Ansible job output.
 * The Vite dev-proxy routes /logs/ws/* → ws://localhost:8000/logs/ws/*
 * In production, nginx handles the same proxy so the path is identical.
 */
export function createLogSocket(jobId, onMessage, onClose) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host     = window.location.host
  const wsUrl    = `${protocol}://${host}/logs/ws/${jobId}`

  const ws = new WebSocket(wsUrl)
  ws.onopen    = () => console.debug('[WS OPEN]', wsUrl)
  ws.onmessage = (evt) => { if (evt.data !== '__ping__') onMessage(evt.data) }
  ws.onclose   = () => { console.debug('[WS CLOSED]', jobId); onClose?.() }
  ws.onerror   = (e) => console.error('[WS ERROR]', e)
  return ws
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket factory — live log-file tail (logtail route)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Tail a named backend log file via WebSocket.
 * @param {'app'|'audit'} logName - allowed log aliases
 * @param {number} lines          - initial tail lines
 * @param {Function} onMessage
 * @param {Function} [onClose]
 */
export function createLogtailSocket(logName, lines = 50, onMessage, onClose) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host     = window.location.host
  const wsUrl    = `${protocol}://${host}/logtail/${logName}?lines=${lines}`

  const ws = new WebSocket(wsUrl)
  ws.onopen    = () => console.debug('[LOGTAIL OPEN]', wsUrl)
  ws.onmessage = (evt) => onMessage(evt.data)
  ws.onclose   = () => { console.debug('[LOGTAIL CLOSED]', logName); onClose?.() }
  ws.onerror   = (e) => console.error('[LOGTAIL ERROR]', e)
  return ws
}

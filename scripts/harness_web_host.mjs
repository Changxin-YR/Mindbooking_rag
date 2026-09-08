import { mkdir, writeFile } from 'node:fs/promises'
import { createServer as createHttpServer } from 'node:http'
import { spawn } from 'node:child_process'
import { connect, createServer as createTcpServer } from 'node:net'
import { join } from 'node:path'

const repo = process.env.HARNESS_REPO || '/harness'
const homeRoot = process.env.HARNESS_HOME_ROOT || '/harness-data'
const controlPort = Number(process.env.HARNESS_BRIDGE_PORT || '8090')
const publicHost = process.env.HARNESS_PUBLIC_HOST || 'localhost'
const portStart = Number(process.env.HARNESS_PORT_START || '3080')
const portEnd = Number(process.env.HARNESS_PORT_END || '3180')
const idleTimeoutMs = Math.max(60_000, Number(process.env.HARNESS_IDLE_TIMEOUT_SECONDS || '300') * 1_000)
const secret = process.env.HARNESS_BRIDGE_SECRET || 'development-only-harness-bridge-secret'
const backendUrl = (process.env.HARNESS_BACKEND_URL || 'http://backend:80').replace(/\/$/u, '')
const provider = process.env.DEEPSEEK_PROVIDER || 'deepseek-official'
const model = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash'

const instances = new Map()
const usedPorts = new Set()

const json = (res, status, value) => {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(value))
}

const safe = value => String(value).replace(/[^A-Za-z0-9_.-]/gu, '_').slice(0, 96) || 'unknown'

async function readBody(req) {
  let body = ''
  for await (const chunk of req) body += chunk
  if (body.length > 256 * 1024) throw new Error('request too large')
  return JSON.parse(body || '{}')
}

function allocatePort() {
  for (let port = portStart; port <= portEnd; port += 1) {
    if (!usedPorts.has(port)) {
      usedPorts.add(port)
      return port
    }
  }
  throw new Error('no Harness web ports available')
}

async function stopInstance(instance) {
  usedPorts.delete(instance.publicPort)
  instance.proxy.close()
  if (instance.child.exitCode === null) instance.child.kill('SIGTERM')
  instances.delete(instance.key)
}

async function pruneIdleInstances() {
  const cutoff = Date.now() - idleTimeoutMs
  for (const instance of [...instances.values()]) {
    if (instance.lastUsed < cutoff) await stopInstance(instance)
  }
}

function patchText() {
  return [
    '- insert:',
    '    - id: novel-platform-agent-tools',
    "      name: '@deepseek-ai/dsh-mcp-client'",
    '      config:',
    '        serverName: novel_platform',
    '        transport: streamable-http',
    `        url: '${backendUrl}/admin/api/v1/agent/mcp'`,
    '        headers:',
    "          Authorization: !!js '`Bearer ${process.env.AGENT_ACCESS_TOKEN}`'",
    "          X-Agent-Session: !!js 'process.env.AGENT_SESSION_ID'",
    '',
  ].join('\n')
}

async function launchInstance(actorId, sessionId, accessToken) {
  await pruneIdleInstances()
  const key = `${actorId}:${sessionId}`
  const old = instances.get(key)
  if (old && old.accessToken === accessToken) {
    old.lastUsed = Date.now()
    return old.url
  }
  if (old) await stopInstance(old)

  const publicPort = allocatePort()
  const home = join(homeRoot, safe(actorId), safe(sessionId))
  await mkdir(home, { recursive: true })
  const patchPath = join(home, 'agent-tools.cordis.yml')
  await writeFile(patchPath, patchText(), 'utf8')
  const env = {
    ...process.env,
    DSH_HOME: home,
    AGENT_ACCESS_TOKEN: accessToken,
    AGENT_SESSION_ID: sessionId,
    DEEPSEEK_PROVIDER: provider,
    DEEPSEEK_MODEL: model,
  }
  const child = spawn('pnpm', [
    'dsh', '--profile', 'web', '--patch', patchPath, '--no-open', '--host', '127.0.0.1', '--port', '0',
  ], { cwd: repo, env, stdio: ['ignore', 'pipe', 'pipe'] })

  const launchUrl = await new Promise((resolve, reject) => {
    let output = ''
    const timer = setTimeout(() => reject(new Error('Harness web startup timed out')), 120_000)
    const onData = chunk => {
      output += chunk.toString()
      const match = output.match(/dsh web:\s+(http:\/\/127\.0\.0\.1:\d+\/\?token=[^\s]+)/u)
      if (match) {
        clearTimeout(timer)
        resolve(match[1])
      }
    }
    child.stdout.on('data', onData)
    child.stderr.on('data', chunk => { output += chunk.toString() })
    child.once('error', error => { clearTimeout(timer); reject(error) })
    child.once('exit', code => {
      if (code !== null && code !== 0) {
        clearTimeout(timer)
        reject(new Error(`Harness web exited with code ${String(code)}`))
      }
    })
  }).catch(async error => {
    usedPorts.delete(publicPort)
    if (child.exitCode === null) child.kill('SIGTERM')
    throw error
  })

  const childPort = Number(new URL(launchUrl).port)
  let instance
  const touch = () => { if (instance) instance.lastUsed = Date.now() }
  const proxy = createTcpServer(socket => {
    touch()
    const upstream = connect(childPort, '127.0.0.1')
    socket.on('data', touch)
    upstream.on('data', touch)
    upstream.on('error', () => socket.destroy())
    socket.on('error', () => upstream.destroy())
    socket.pipe(upstream)
    upstream.pipe(socket)
  })
  await new Promise((resolve, reject) => {
    proxy.once('error', reject)
    proxy.listen(publicPort, '0.0.0.0', resolve)
  })
  const token = new URL(launchUrl).searchParams.get('token')
  const url = `http://${publicHost}:${String(publicPort)}/?token=${encodeURIComponent(token || '')}`
  instance = { key, actorId, sessionId, accessToken, child, proxy, publicPort, url, lastUsed: Date.now() }
  instances.set(key, instance)
  child.once('exit', () => { if (instances.get(key) === instance) void stopInstance(instance) })
  return url
}

const control = createHttpServer(async (req, res) => {
  if (req.url === '/healthz') return json(res, 200, { status: 'ok' })
  if (req.headers['x-harness-bridge-secret'] !== secret) return json(res, 401, { error: 'unauthorized' })
  try {
    if (req.method === 'POST' && req.url === '/allocate') {
      const body = await readBody(req)
      if (![body.actor_id, body.session_id, body.access_token].every(value => typeof value === 'string' && value.length > 0)) {
        return json(res, 400, { error: 'invalid allocation request' })
      }
      return json(res, 200, { url: await launchInstance(body.actor_id, body.session_id, body.access_token), session_id: body.session_id })
    }
    if (req.method === 'POST' && req.url === '/release') {
      const body = await readBody(req)
      const instance = instances.get(`${body.actor_id}:${body.session_id}`)
      if (instance) await stopInstance(instance)
      return json(res, 200, { released: true })
    }
    return json(res, 404, { error: 'not found' })
  } catch (error) {
    console.error(`harness bridge: ${error instanceof Error ? error.message : String(error)}`)
    return json(res, 503, { error: 'Harness web unavailable' })
  }
})

control.listen(controlPort, '0.0.0.0', () => console.log(`harness bridge listening on ${String(controlPort)}`))
setInterval(() => { void pruneIdleInstances() }, Math.min(idleTimeoutMs, 60_000)).unref()

const shutdown = async () => {
  for (const instance of [...instances.values()]) await stopInstance(instance)
  control.close()
  process.exit(0)
}
process.once('SIGTERM', shutdown)
process.once('SIGINT', shutdown)

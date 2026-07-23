import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './schema'

// Interim: the list endpoint is HTTP Basic (ops/changeme) until #31b brings the cookie session.
const OPS_USER = import.meta.env.VITE_OPS_USER ?? 'ops'
const OPS_PASSWORD = import.meta.env.VITE_OPS_PASSWORD ?? 'changeme'

const opsAuth: Middleware = {
  onRequest({ request }) {
    request.headers.set('Authorization', `Basic ${btoa(`${OPS_USER}:${OPS_PASSWORD}`)}`)
    return request
  },
}

// baseUrl '' — schema paths already carry the /api prefix, so calls are same-origin.
export const api = createClient<paths>({ baseUrl: '' })
api.use(opsAuth)

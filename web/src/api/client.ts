import createClient from 'openapi-fetch'

import type { paths } from './schema'

// baseUrl '' — schema paths already carry the /api prefix, so calls are same-origin and the
// signed `uw_session` cookie rides along automatically. Auth is the session, set at /api/auth/login.
export const api = createClient<paths>({ baseUrl: '' })

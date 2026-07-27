import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import { HeroUIProvider } from '@heroui/react'
import './index.css'
import AppRouter from './AppRouter.tsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

/**
 * Auth0 requires the SPA's redirect_uri to be explicitly allow-listed.
 * Many Auth0 setups include `http://localhost:5173` but not `http://127.0.0.1:5173`.
 * Normalize localhost IP to hostname to avoid "Callback URL mismatch" during local dev.
 */
const redirectUri = (() => {
  try {
    const url = new URL(window.location.href)
    if (url.hostname === '127.0.0.1') {
      url.hostname = 'localhost'
    }
    url.pathname = ''
    url.search = ''
    url.hash = ''
    return url.toString().replace(/\/$/, '')
  } catch {
    return window.location.origin
  }
})()

// Debug: Log Auth0 config (only in development or if explicitly enabled)
if (import.meta.env.DEV || import.meta.env.VITE_DEBUG_AUTH0) {
  console.log('Auth0 Configuration:', {
    domain: domain || 'NOT SET',
    clientId: clientId ? `${clientId.substring(0, 10)}...` : 'NOT SET',
    audience: audience || 'NOT SET',
    hasDomain: !!domain,
    hasClientId: !!clientId,
    redirectUri,
  })
}

// Auth0 is optional - only wrap with Auth0Provider if configured
const AppWithAuth = domain && clientId ? (
  <Auth0Provider
    domain={domain}
    clientId={clientId}
    authorizationParams={{
      redirect_uri: redirectUri,
      audience: audience,
    }}
  >
    <HeroUIProvider>
      <AppRouter />
    </HeroUIProvider>
  </Auth0Provider>
) : (
  <HeroUIProvider>
    <AppRouter />
  </HeroUIProvider>
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {AppWithAuth}
  </StrictMode>,
)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import { HeroUIProvider } from '@heroui/react'
import './index.css'
import App from './App.tsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

// Debug: Log Auth0 config (only in development or if explicitly enabled)
if (import.meta.env.DEV || import.meta.env.VITE_DEBUG_AUTH0) {
  console.log('Auth0 Configuration:', {
    domain: domain || 'NOT SET',
    clientId: clientId ? `${clientId.substring(0, 10)}...` : 'NOT SET',
    audience: audience || 'NOT SET',
    hasDomain: !!domain,
    hasClientId: !!clientId,
  })
}

// Auth0 is optional - only wrap with Auth0Provider if configured
const AppWithAuth = domain && clientId ? (
  <Auth0Provider
    domain={domain}
    clientId={clientId}
    authorizationParams={{
      redirect_uri: window.location.origin,
      audience: audience,
    }}
  >
    <HeroUIProvider>
      <App />
    </HeroUIProvider>
  </Auth0Provider>
) : (
  <HeroUIProvider>
    <App />
  </HeroUIProvider>
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {AppWithAuth}
  </StrictMode>,
)

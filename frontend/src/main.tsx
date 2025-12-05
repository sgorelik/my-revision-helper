import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import { HeroUIProvider } from '@heroui/react'
import './index.css'
import App from './App.tsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

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

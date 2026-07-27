/**
 * Auth utilities for Auth0 integration.
 * 
 * Provides a custom hook for authentication that works with or without Auth0 configured.
 */

import { useAuth0 } from '@auth0/auth0-react'

/**
 * Whether Auth0 is set up for this build.
 *
 * Matters because useAuth0 reports isLoading: true forever when there is no
 * Auth0Provider above it, so anything waiting on auth to settle has to know
 * not to wait at all in the anonymous configuration.
 */
export const isAuth0Configured = Boolean(
  import.meta.env.VITE_AUTH0_DOMAIN && import.meta.env.VITE_AUTH0_CLIENT_ID,
)

/**
 * Keep logout returnTo aligned with Auth0 allow-lists.
 * If the app is accessed via 127.0.0.1 in dev, normalize to localhost to avoid
 * Auth0 "Invalid logout URL" / allowlist issues.
 */
const getAuth0ReturnTo = (): string => {
  try {
    const url = new URL(window.location.href)
    if (url.hostname === '127.0.0.1') url.hostname = 'localhost'
    url.pathname = ''
    url.search = ''
    url.hash = ''
    return url.toString().replace(/\/$/, '')
  } catch {
    return window.location.origin
  }
}

export const useAuth = () => {
  const { 
    user, 
    isAuthenticated, 
    isLoading, 
    loginWithRedirect, 
    logout,
    getAccessTokenSilently 
  } = useAuth0()
  
  const getToken = async (): Promise<string | null> => {
    // Early return if not authenticated - no need to call Auth0
    if (!isAuthenticated) {
      return null
    }
    try {
      return await getAccessTokenSilently()
    } catch (error) {
      console.warn('Failed to get access token:', error)
      return null
    }
  }
  
  return {
    user,
    isAuthenticated,
    isLoading,
    login: () => loginWithRedirect(),
    logout: () => logout({ 
      logoutParams: { 
        returnTo: getAuth0ReturnTo(),
      } 
    }),
    getToken,
  }
}


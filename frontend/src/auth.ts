/**
 * Auth utilities for Auth0 integration.
 * 
 * Provides a custom hook for authentication that works with or without Auth0 configured.
 */

import { useAuth0 } from '@auth0/auth0-react'

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
        returnTo: window.location.origin 
      } 
    }),
    getToken,
  }
}


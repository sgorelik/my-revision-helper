import { useState } from 'react'

interface LogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  showPlaceholder?: boolean
}

const sizeClasses = {
  sm: 'w-6 h-6',
  md: 'w-10 h-10',
  lg: 'w-12 h-12',
  xl: 'w-20 h-20',
}

export default function Logo({ size = 'md', className = '', showPlaceholder = true }: LogoProps) {
  const [imageError, setImageError] = useState(false)
  const sizeClass = sizeClasses[size]

  if (imageError && showPlaceholder) {
    return (
      <div className={`${sizeClass} bg-orange-200 rounded-lg flex items-center justify-center ${className}`}>
        <span className="text-2xl">🧮</span>
      </div>
    )
  }

  return (
    <img 
      src="/calculator-logo.png" 
      alt="Calculator Logo" 
      className={`${sizeClass} object-contain ${className}`}
      onError={() => setImageError(true)}
    />
  )
}


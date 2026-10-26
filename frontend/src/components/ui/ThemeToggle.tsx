import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { useTheme } from '../../theme/ThemeContext'
import {
  themePreferenceLabel,
  type ThemePreference,
} from '../../theme/theme'

const OPTIONS: Array<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: 'Система' },
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Тёмная' },
]

function IconSun() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
      <path
        d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconMoon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M21 14.5A8.5 8.5 0 119.5 3 7 7 0 0021 14.5z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconSystem() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="4" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M8 21h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function IconCheck() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5 12.5l5 5L19 7"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function PreferenceIcon({ value }: { value: ThemePreference }) {
  if (value === 'light') return <IconSun />
  if (value === 'dark') return <IconMoon />
  return <IconSystem />
}

export function ThemeToggle({ className = '' }: { className?: string }) {
  const { preference, setPreference } = useTheme()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(() =>
    Math.max(0, OPTIONS.findIndex((o) => o.value === preference)),
  )
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    const idx = Math.max(0, OPTIONS.findIndex((o) => o.value === preference))
    setActiveIndex(idx)
    const id = window.setTimeout(() => optionRefs.current[idx]?.focus(), 0)
    return () => window.clearTimeout(id)
  }, [open, preference])

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      const root = rootRef.current
      if (!root) return
      if (event.target instanceof Node && !root.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  function selectPreference(value: ThemePreference) {
    setPreference(value)
    setOpen(false)
    triggerRef.current?.focus()
  }

  function toggleOpen() {
    setOpen((prev) => !prev)
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleOpen()
    }
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
      triggerRef.current?.focus()
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      const next = (activeIndex + 1) % OPTIONS.length
      setActiveIndex(next)
      optionRefs.current[next]?.focus()
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      const next = (activeIndex - 1 + OPTIONS.length) % OPTIONS.length
      setActiveIndex(next)
      optionRefs.current[next]?.focus()
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      setActiveIndex(0)
      optionRefs.current[0]?.focus()
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      const last = OPTIONS.length - 1
      setActiveIndex(last)
      optionRefs.current[last]?.focus()
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      selectPreference(OPTIONS[activeIndex].value)
    }
  }

  return (
    <div className={`theme-toggle-wrap ${className}`.trim()} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="theme-toggle"
        aria-label="Выбрать тему оформления"
        title={themePreferenceLabel(preference)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={toggleOpen}
        onKeyDown={onTriggerKeyDown}
      >
        <PreferenceIcon value={preference} />
      </button>

      {open ? (
        <div
          id={menuId}
          className="theme-menu"
          role="menu"
          aria-label="Оформление"
          onKeyDown={onMenuKeyDown}
        >
          <div className="theme-menu-title">Оформление</div>
          {OPTIONS.map((option, index) => {
            const selected = preference === option.value
            return (
              <button
                key={option.value}
                ref={(node) => {
                  optionRefs.current[index] = node
                }}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                className={`theme-menu-item${selected ? ' is-selected' : ''}${
                  index === activeIndex ? ' is-active' : ''
                }`}
                tabIndex={index === activeIndex ? 0 : -1}
                onClick={() => selectPreference(option.value)}
                onMouseEnter={() => setActiveIndex(index)}
              >
                <span className="theme-menu-item-icon">
                  <PreferenceIcon value={option.value} />
                </span>
                <span className="theme-menu-item-label">{option.label}</span>
                {selected ? (
                  <span className="theme-menu-item-check" aria-hidden>
                    <IconCheck />
                  </span>
                ) : (
                  <span className="theme-menu-item-check" aria-hidden />
                )}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

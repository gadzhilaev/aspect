type Props = {
  variant: 'loading' | 'empty' | 'error'
  title: string
  description?: string
  onRetry?: () => void
}

export function StateBlock({ variant, title, description, onRetry }: Props) {
  return (
    <div className={`state-block state-${variant}`} role="status">
      <div className="state-title">{title}</div>
      {description ? <p className="state-desc">{description}</p> : null}
      {variant === 'error' && onRetry ? (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Повторить
        </button>
      ) : null}
    </div>
  )
}

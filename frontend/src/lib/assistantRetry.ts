/**
 * client_message_id policy for assistant send / manual retry (stage 4.5.1).
 *
 * - Redelivery of the same request (manual retry after transient failure) → same id.
 * - Explicit new attempt after a known terminal loop failure → new id (new cycle).
 * - Ordinary new send (not a retry click) → always new id.
 * - No automatic paid retry after timeout (caller must click).
 */

export function normalizeClientMessageText(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
}

/** Terminal failures: same id must replay incomplete error, not start a silent new cycle. */
export function isTerminalAssistantFailure(code: string | null | undefined): boolean {
  if (!code) return false
  if (code.startsWith('ASSISTANT_LOOP_')) return true
  if (code === 'ASSISTANT_MESSAGE_ID_CONFLICT') return true
  return false
}

export function isTransientAssistantFailure(code: string | null | undefined): boolean {
  if (!code) return true
  if (code === 'ASSISTANT_MESSAGE_IN_PROGRESS') return true
  if (code === 'PROVIDER_UNAVAILABLE') return true
  return !isTerminalAssistantFailure(code)
}

export function chooseClientMessageId(opts: {
  quick?: boolean
  text: string
  previousId: string | null
  previousFailureCode: string | null
  /** True only when the user clicked «Повторить» (or equivalent). */
  isRetry: boolean
  newId: () => string
  quickId: (text: string) => string
}): string {
  if (opts.quick) return opts.quickId(opts.text)
  if (!opts.isRetry) return opts.newId()
  if (isTerminalAssistantFailure(opts.previousFailureCode)) {
    return opts.newId()
  }
  if (opts.previousId && isTransientAssistantFailure(opts.previousFailureCode)) {
    return opts.previousId
  }
  return opts.newId()
}

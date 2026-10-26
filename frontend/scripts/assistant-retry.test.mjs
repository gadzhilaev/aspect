/**
 * Unit tests for assistant client_message_id retry policy (stage 4.5.1).
 * node:test + --experimental-strip-types — no browser.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const libUrl = pathToFileURL(join(root, 'src/lib/assistantRetry.ts')).href

const {
  chooseClientMessageId,
  isTerminalAssistantFailure,
  isTransientAssistantFailure,
  normalizeClientMessageText,
} = await import(libUrl)

describe('normalizeClientMessageText', () => {
  it('strips edges and unifies newlines without collapsing inner spaces', () => {
    assert.equal(normalizeClientMessageText('  a  b\r\nc  '), 'a  b\nc')
  })
})

describe('failure classification', () => {
  it('treats ASSISTANT_LOOP_* as terminal', () => {
    assert.equal(isTerminalAssistantFailure('ASSISTANT_LOOP_TIMEOUT'), true)
    assert.equal(isTerminalAssistantFailure('ASSISTANT_MESSAGE_IN_PROGRESS'), false)
  })

  it('treats IN_PROGRESS and missing code as transient', () => {
    assert.equal(isTransientAssistantFailure('ASSISTANT_MESSAGE_IN_PROGRESS'), true)
    assert.equal(isTransientAssistantFailure(null), true)
  })
})

describe('chooseClientMessageId', () => {
  const newId = () => 'new-id'
  const quickId = (t) => `quick:${t}`

  it('always issues a fresh id for a normal (non-retry) send', () => {
    assert.equal(
      chooseClientMessageId({
        text: 'q',
        previousId: 'old-id',
        previousFailureCode: null,
        isRetry: false,
        newId,
        quickId,
      }),
      'new-id',
    )
  })

  it('uses new id after terminal loop failure on retry', () => {
    assert.equal(
      chooseClientMessageId({
        text: 'q',
        previousId: 'old-id',
        previousFailureCode: 'ASSISTANT_LOOP_TIMEOUT',
        isRetry: true,
        newId,
        quickId,
      }),
      'new-id',
    )
  })

  it('reuses id for IN_PROGRESS redelivery', () => {
    assert.equal(
      chooseClientMessageId({
        text: 'q',
        previousId: 'old-id',
        previousFailureCode: 'ASSISTANT_MESSAGE_IN_PROGRESS',
        isRetry: true,
        newId,
        quickId,
      }),
      'old-id',
    )
  })

  it('reuses id for network-like failure on retry', () => {
    assert.equal(
      chooseClientMessageId({
        text: 'q',
        previousId: 'old-id',
        previousFailureCode: null,
        isRetry: true,
        newId,
        quickId,
      }),
      'old-id',
    )
  })
})

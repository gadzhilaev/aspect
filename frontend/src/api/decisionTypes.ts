export type ActionItemStatus = 'todo' | 'in_progress' | 'done'

export type DecisionActionItem = {
  id: string
  title: string
  status: ActionItemStatus
  status_label: string
  assignee_name: string | null
  due_at: string | null
}

export type DecisionProgress = {
  done: number
  total: number
  label: string
}

export type DecisionDetail = {
  id: string
  status: string
  status_label: string
  title: string
  summary: string
  expected_effect: string | null
  horizon: string | null
  confidence: number | null
  progress: DecisionProgress
  event: {
    id: string
    title: string
    category: string
    category_label: string
    occurred_at: string | null
    is_demo: boolean
  }
  scenario: {
    id: string
    title: string
    reason: string
    is_estimate: boolean
    presentation?: Record<string, unknown> | null
    model_version?: string | null
  }
  action_items: DecisionActionItem[]
  conversation_href: string | null
  news_href: string
  created_at: string
  disclaimer: string
  cancelled_at?: string | null
  cancel_reason?: string | null
  actions_locked?: boolean
}

export type ActionItemPatchResult = DecisionActionItem & {
  progress: DecisionProgress
}

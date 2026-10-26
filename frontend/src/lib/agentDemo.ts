/** Agent-loop demo stand helpers (stage 4.8). Gated by Vite env only. */

export function isAgentDemoStand(): boolean {
  return import.meta.env.VITE_AGENT_DEMO === 'true'
}

/** Post-login / CTA landing when the demo stand flag is on. */
export function agentDemoHomePath(): string {
  return '/agent-demo'
}

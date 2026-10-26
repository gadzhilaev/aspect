/** Profile matches are thematic relevance, never a numerical impact. */
export function isProfileOnly(event: { score_kind?: string; inclusion_bases?: string[] }): boolean {
  if (event.score_kind === 'case_profile_match' || event.score_kind === 'industry_profile_match') return true
  const bases = event.inclusion_bases ?? []
  return (bases.includes('case_profile') || bases.includes('industry_profile')) &&
    !bases.includes('calculated_impact') && !bases.includes('event_severity_signal')
}

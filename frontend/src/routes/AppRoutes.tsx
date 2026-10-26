import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { SiteLayout } from '../layouts/SiteLayout'
import { AboutPage } from '../pages/AboutPage'
import { AccountSettingsPage } from '../pages/AccountSettingsPage'
import { IndustriesPage, OpportunitiesPage, SoftPlaceholder } from '../pages/SimpleContentPage'
import { AgentDemoPage } from '../pages/AgentDemoPage'
import { CompanyPage } from '../pages/CompanyPage'
import { CompanySectionPage } from '../pages/CompanySectionPage'
import { CompanySetupPage } from '../pages/CompanySetupPage'
import { ForYouPage } from '../pages/ForYouPage'
import { HomePage } from '../pages/HomePage'
import { AssistantPage } from '../pages/AssistantPage'
import { ImpactPage } from '../pages/ImpactPage'
import { LoginPage } from '../pages/LoginPage'
import { NewsDetailPage } from '../pages/NewsDetailPage'
import { NewsPage } from '../pages/NewsPage'
import { RegisterPage } from '../pages/RegisterPage'
import { DecisionPage } from '../pages/DecisionPage'
import { NotificationsPage } from '../pages/NotificationsPage'
import { SupportChatPage } from '../pages/SupportChatPage'
import { ScenariosPage } from '../pages/ScenariosPage'
import { BankFragmentPage } from '../pages/BankFragmentPage'
import { isAgentDemoStand } from '../lib/agentDemo'
import { ProtectedRoute } from './ProtectedRoute'

/** Legacy impact CTA → real scenarios workspace, filtered by event. */
function EventScenariosRedirect() {
  const { eventId } = useParams()
  const target = eventId ? `/scenarios?event=${encodeURIComponent(eventId)}` : '/scenarios'
  return <Navigate to={target} replace />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route index element={<HomePage />} />
        <Route path="news" element={<NewsPage />} />
        <Route
          path="news/for-you"
          element={
            <ProtectedRoute>
              <ForYouPage />
            </ProtectedRoute>
          }
        />
        <Route path="news/markets" element={<NewsPage />} />
        <Route path="news/industries" element={<IndustriesPage />} />
        <Route path="news/opportunities" element={<OpportunitiesPage />} />
        <Route path="news/:eventId" element={<NewsDetailPage />} />
        <Route path="industries" element={<Navigate to="/news/industries" replace />} />
        <Route path="opportunities" element={<Navigate to="/news/opportunities" replace />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        {isAgentDemoStand() ? (
          <Route
            path="agent-demo"
            element={
              <ProtectedRoute>
                <AgentDemoPage />
              </ProtectedRoute>
            }
          />
        ) : null}

        <Route path="for-you" element={<Navigate to="/news/for-you" replace />} />
        <Route
          path="scenarios"
          element={
            <ProtectedRoute>
              <ScenariosPage />
            </ProtectedRoute>
          }
        />
        <Route path="company" element={<CompanyPage />} />
        <Route
          path="company/setup"
          element={
            <ProtectedRoute>
              <CompanySetupPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="company/:sectionId"
          element={
            <ProtectedRoute>
              <CompanySectionPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="events/:eventId/impact"
          element={
            <ProtectedRoute>
              <ImpactPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="events/:eventId/assistant"
          element={
            <ProtectedRoute>
              <AssistantPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="bank-materials/fragments/:fragmentId"
          element={
            <ProtectedRoute>
              <BankFragmentPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="events/:eventId/scenarios"
          element={
            <ProtectedRoute>
              <EventScenariosRedirect />
            </ProtectedRoute>
          }
        />
        <Route
          path="decisions"
          element={
            <ProtectedRoute>
              <SoftPlaceholder
                title="Решения"
                lead="Сохранённые планы действий будут жить рядом с вашей лентой."
              />
            </ProtectedRoute>
          }
        />
        <Route
          path="decisions/:decisionId"
          element={
            <ProtectedRoute>
              <DecisionPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="notifications"
          element={
            <ProtectedRoute>
              <NotificationsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings"
          element={
            <ProtectedRoute>
              <AccountSettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="support"
          element={
            <ProtectedRoute>
              <SupportChatPage />
            </ProtectedRoute>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

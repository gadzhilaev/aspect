import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { AppRoutes } from './routes/AppRoutes'
import { ThemeProvider } from './theme/ThemeContext'
import './styles/global.css'
import './styles/site.css'
import './styles/mobile-align.css'
import './styles/home.css'
import './styles/about.css'
import './styles/company.css'
import './styles/scenarios.css'
import './styles/decision.css'
import './styles/assistant.css'
import './styles/bank-materials.css'
import './styles/notifications.css'
import './styles/support.css'

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
      <ThemeProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}

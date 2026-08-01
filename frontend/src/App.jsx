import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import NewTest from './pages/NewTest.jsx'
import Screening from './pages/Screening.jsx'
import Symptoms from './pages/Symptoms.jsx'
import Otoscopy from './pages/Otoscopy.jsx'
import Immittance from './pages/Immittance.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Simulator from './pages/Simulator.jsx'
import Progression from './pages/Progression.jsx'
import Batch from './pages/Batch.jsx'
import Records from './pages/Records.jsx'
import ListeningLab from './pages/ListeningLab.jsx'

export default function App() {
  return (
    <Layout>
      <a href="#main-content" className="skip-link rounded-lg bg-teal-600 px-3 py-2 text-[13px] font-semibold text-white">
        Skip to main content
      </a>
      <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Navigate to="/new-test" replace />} />
        <Route path="/new-test" element={<NewTest />} />
        <Route path="/symptoms" element={<Symptoms />} />
        <Route path="/otoscopy" element={<Otoscopy />} />
        <Route path="/immittance" element={<Immittance />} />
        <Route path="/screening" element={<Screening />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/simulator" element={<Simulator />} />
        <Route path="/progression" element={<Progression />} />
        <Route path="/batch" element={<Batch />} />
        <Route path="/listening-lab" element={<ListeningLab />} />
        <Route path="/records" element={<Records />} />
      </Routes>
      </ErrorBoundary>
    </Layout>
  )
}

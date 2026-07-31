import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import NewTest from './pages/NewTest.jsx'
import Screening from './pages/Screening.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Simulator from './pages/Simulator.jsx'
import Progression from './pages/Progression.jsx'
import Batch from './pages/Batch.jsx'
import Records from './pages/Records.jsx'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/new-test" replace />} />
        <Route path="/new-test" element={<NewTest />} />
        <Route path="/screening" element={<Screening />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/simulator" element={<Simulator />} />
        <Route path="/progression" element={<Progression />} />
        <Route path="/batch" element={<Batch />} />
        <Route path="/records" element={<Records />} />
      </Routes>
    </Layout>
  )
}

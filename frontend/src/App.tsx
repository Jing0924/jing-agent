import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/app-shell'
import { CalendarPage } from '@/pages/calendar-page'
import { KnowledgeChatPage } from '@/pages/knowledge-chat-page'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<KnowledgeChatPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

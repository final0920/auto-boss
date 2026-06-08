import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'
import { DeviceProvider } from './lib/device-context'
import { I18nProvider } from './lib/i18n'
import './styles/globals.css'

const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

const rootEl = document.getElementById('root')!
createRoot(rootEl).render(
  <StrictMode>
    <I18nProvider>
      <DeviceProvider>
        <RouterProvider router={router} />
      </DeviceProvider>
    </I18nProvider>
  </StrictMode>,
)

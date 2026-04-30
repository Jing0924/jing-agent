import { NavLink, Outlet } from 'react-router-dom'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function AppShell() {
  return (
    <main className="flex w-full max-w-2xl flex-1 flex-col gap-8 self-center px-6 py-8 text-left">
      <nav
        className="flex flex-wrap gap-2 border-b border-border pb-4"
        aria-label="主要導覽"
      >
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            cn(
              buttonVariants({
                variant: isActive ? 'default' : 'outline',
                size: 'lg',
              }),
            )
          }
        >
          知識庫問答
        </NavLink>
        <NavLink
          to="/calendar"
          className={({ isActive }) =>
            cn(
              buttonVariants({
                variant: isActive ? 'default' : 'outline',
                size: 'lg',
              }),
            )
          }
        >
          行事曆
        </NavLink>
      </nav>
      <Outlet />
    </main>
  )
}

export { AppShell }

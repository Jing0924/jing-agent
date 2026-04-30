import { Link, NavLink, Outlet } from 'react-router-dom'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function AppShell() {
  return (
    <div className="flex min-h-svh w-full flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-border bg-background/80 px-6 py-3 backdrop-blur">
        <Link
          to="/"
          className="brand-heading-gradient text-lg font-semibold tracking-tight"
        >
          Jing Agent
        </Link>
        <nav className="flex flex-wrap justify-end gap-2" aria-label="主要導覽">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cn(
                buttonVariants({
                  variant: isActive ? 'default' : 'outline',
                  size: 'default',
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
                  size: 'default',
                }),
              )
            }
          >
            管理行事曆
          </NavLink>
        </nav>
      </header>
      <main className="flex w-full max-w-2xl flex-1 flex-col gap-8 self-center px-6 py-8 text-left">
        <Outlet />
      </main>
    </div>
  )
}

export { AppShell }

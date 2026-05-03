import { Link, NavLink, Outlet } from 'react-router-dom'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function AppShell() {
  return (
    <div className="flex min-h-svh w-full flex-col">
      <header
        className={cn(
          'sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-background/80 backdrop-blur',
          'pt-[max(0.75rem,env(safe-area-inset-top,0px))] pb-2.5 sm:gap-4 sm:py-3',
          'pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))]',
          'sm:pl-[max(1.5rem,env(safe-area-inset-left,0px))] sm:pr-[max(1.5rem,env(safe-area-inset-right,0px))]',
        )}
      >
        <Link
          to="/"
          className="brand-heading-gradient min-w-0 shrink text-lg font-semibold tracking-tight"
        >
          Jing Agent
        </Link>
        <nav className="flex shrink-0 flex-nowrap justify-end gap-1.5 sm:gap-2" aria-label="主要導覽">
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
            <span className="sm:hidden">問答</span>
            <span className="hidden sm:inline">知識庫問答</span>
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
            <span className="sm:hidden">行事曆</span>
            <span className="hidden sm:inline">管理行事曆</span>
          </NavLink>
        </nav>
      </header>
      <main
        className={cn(
          'flex w-full max-w-2xl flex-1 flex-col gap-8 self-center text-left',
          'py-6 sm:py-8',
          'pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))]',
          'sm:pl-[max(1.5rem,env(safe-area-inset-left,0px))] sm:pr-[max(1.5rem,env(safe-area-inset-right,0px))]',
        )}
      >
        <Outlet />
      </main>
    </div>
  )
}

export { AppShell }

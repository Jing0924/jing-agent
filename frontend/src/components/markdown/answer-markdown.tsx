import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { cn } from '@/lib/utils'

type Props = {
  content: string
  className?: string
}

const components: Components = {
  a: ({ node: _node, ...props }) => (
    <a
      {...props}
      target="_blank"
      rel="noreferrer noopener"
      className="break-all text-primary underline underline-offset-2 hover:opacity-80"
    />
  ),
  p: ({ node: _node, ...props }) => (
    <p {...props} className="leading-relaxed" />
  ),
  ul: ({ node: _node, ...props }) => (
    <ul {...props} className="list-disc space-y-1 pl-5" />
  ),
  ol: ({ node: _node, ...props }) => (
    <ol {...props} className="list-decimal space-y-1 pl-5" />
  ),
  code: ({ node: _node, className, children, ...props }) =>
    className?.includes('language-') ? (
      <pre className="overflow-x-auto rounded-md bg-muted p-3 text-sm">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    ) : (
      <code
        className="rounded bg-muted px-1 py-0.5 text-[0.85em]"
        {...props}
      >
        {children}
      </code>
    ),
  table: ({ node: _node, ...props }) => (
    <div className="overflow-x-auto">
      <table {...props} className="w-full border-collapse text-sm" />
    </div>
  ),
  th: ({ node: _node, ...props }) => (
    <th
      {...props}
      className="border border-border px-2 py-1 text-left font-medium"
    />
  ),
  td: ({ node: _node, ...props }) => (
    <td {...props} className="border border-border px-2 py-1 align-top" />
  ),
}

export function AnswerMarkdown({ content, className }: Props) {
  return (
    <div
      className={cn(
        'space-y-2 break-words text-[0.95rem] leading-relaxed text-card-foreground',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

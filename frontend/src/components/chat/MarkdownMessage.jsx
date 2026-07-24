import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'

/**
 * MarkdownMessage — renders Aisha's responses as rich markdown.
 *
 * Supports: code blocks, inline code, tables, lists, headings,
 * bold/italic, links, and syntax highlighting.
 *
 * Falls back to plain text rendering if content has no markdown.
 */
export default function MarkdownMessage({ content }) {
  if (!content) return null

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Open external links in new tab
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          // Wrap code blocks for overflow handling
          pre: ({ node, ...props }) => (
            <pre className="md-pre" {...props} />
          ),
          code: ({ node, className, children, ...props }) => {
            const isInline = !className
            if (isInline) {
              return <code className="md-inline-code" {...props}>{children}</code>
            }
            return <code className={className} {...props}>{children}</code>
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

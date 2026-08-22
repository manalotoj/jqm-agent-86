import type { AnchorHTMLAttributes, ComponentPropsWithoutRef, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const SAFE_LINK_PROTOCOL = /^(https?:|mailto:)/i;

type MarkdownLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  children?: ReactNode;
};

function MarkdownLink({ children, href, ...props }: MarkdownLinkProps) {
  if (!href || !SAFE_LINK_PROTOCOL.test(href)) {
    return <>{children}</>;
  }

  return (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-primary underline underline-offset-2 hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {children}
    </a>
  );
}

function Code({ children, ...props }: ComponentPropsWithoutRef<"code">) {
  return (
    <code {...props} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.8125rem] break-words">
      {children}
    </code>
  );
}

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="mt-2 min-w-0 text-sm leading-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: MarkdownLink,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-muted-foreground/40 pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          code: Code,
          h1: ({ children }) => <h1 className="mt-4 mb-2 text-xl font-semibold tracking-tight">{children}</h1>,
          h2: ({ children }) => <h2 className="mt-4 mb-2 text-lg font-semibold tracking-tight">{children}</h2>,
          h3: ({ children }) => <h3 className="mt-3 mb-1 text-base font-semibold">{children}</h3>,
          hr: () => <hr className="my-4 border-border" />,
          li: ({ children }) => <li className="pl-1">{children}</li>,
          ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          pre: ({ children }) => (
            <pre className="my-3 overflow-x-auto rounded-lg border bg-muted/60 p-3 text-[0.8125rem] leading-5">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg border">
              <table className="w-full border-collapse text-left text-[0.8125rem]">{children}</table>
            </div>
          ),
          td: ({ children }) => <td className="border-t px-3 py-2 align-top">{children}</td>,
          th: ({ children }) => <th className="bg-muted/60 px-3 py-2 font-semibold">{children}</th>,
          ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
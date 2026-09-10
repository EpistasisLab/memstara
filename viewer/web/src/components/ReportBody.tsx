import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Model output is untrusted: render Markdown without evaluating embedded HTML. */
export default function ReportBody({ text }: { text: string }) {
  return <div className="text-sm leading-relaxed text-ink [&_h1]:mb-4 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-6 [&_h2]:text-lg [&_h2]:font-bold [&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:font-bold [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_th]:bg-paper [&_th]:p-2 [&_td]:border-t [&_td]:border-paper-line [&_td]:p-2 [&_a]:text-blue-700 [&_a]:underline [&_hr]:my-5">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
      img: ({ alt }) => <span>{alt || "Image omitted"}</span>,
      table: ({ children }) => <div className="my-3 overflow-x-auto"><table className="w-full text-left text-xs">{children}</table></div>,
      a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    }}>{text}</Markdown>
  </div>;
}

import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
export default function SkillMarkdown({content}:{content:string}) {
 return <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>;
}

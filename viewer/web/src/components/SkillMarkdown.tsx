import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { displayMarkdown } from '../lib/displayMarkdown';
const plugins = [remarkGfm, displayMarkdown];
export default function SkillMarkdown({content}:{content:string}) {
 return <Markdown remarkPlugins={plugins} skipHtml>{content}</Markdown>;
}

import { displayText } from '../lib/displayText';
import * as Tooltip from '@radix-ui/react-tooltip';
import type { ReactElement } from 'react';

/** No DOM wrapper: native details/summary semantics remain intact. */
export default function DetailPreview({title,text,children}:{title:string;text:string;children:ReactElement}) {
  return <Tooltip.Root delayDuration={300}><Tooltip.Trigger asChild data-context-help-managed>{children}</Tooltip.Trigger>
    <Tooltip.Portal><Tooltip.Content side="bottom" align="start" sideOffset={6} collisionPadding={12}
      className="telemetry-detail-preview"><strong>{displayText(title)}</strong><p>{displayText(text)}</p></Tooltip.Content></Tooltip.Portal>
  </Tooltip.Root>;
}

import { Handle, Position } from '@xyflow/react';
import { Database } from 'lucide-react';

/** An application database with selected table children; not a complete schema. */
export default function FloorDatabaseNode() {
  return <div className="floor-database" role="group" aria-label="Memstara database: selected Blackboard and Results tables; question records also exist">
    <Handle type="target" position={Position.Bottom} className="!opacity-0"/>
    <header><Database size={22} aria-hidden="true"/><div><strong>Memstara DB</strong><span>Application DB · selected tables</span></div></header>
  </div>;
}

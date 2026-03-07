'use client';

import { Suspense } from 'react';
import WorkflowBuilder from '@/components/workflow/WorkflowBuilder';

export default function WorkflowPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen bg-gray-950 text-gray-400">Loading…</div>}>
      <WorkflowBuilder />
    </Suspense>
  );
}

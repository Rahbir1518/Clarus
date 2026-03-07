'use client';

import { type DragEvent } from 'react';
import { NODE_CATALOGUE, CATEGORY_STYLES, type CatalogueNode } from './types';

interface PaletteItemProps {
  node: CatalogueNode;
  nodeType: string;
  styles: (typeof CATEGORY_STYLES)[keyof typeof CATEGORY_STYLES];
}

function PaletteItem({ node, nodeType, styles }: PaletteItemProps) {
  const onDragStart = (event: DragEvent<HTMLDivElement>) => {
    event.dataTransfer.setData(
      'application/reactflow',
      JSON.stringify({ ...node, nodeType })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      draggable
      onDragStart={onDragStart}
      className={`
        px-3 py-2.5 rounded-lg border cursor-grab active:cursor-grabbing
        transition-all duration-100 select-none
        hover:scale-[1.02] hover:shadow-md active:scale-[0.98]
        ${styles.palette}
      `}
    >
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${styles.dot}`} />
        <span className="text-xs font-semibold text-gray-200 truncate">{node.label}</span>
      </div>
      <p className="text-[10px] text-gray-500 mt-0.5 ml-3.5 font-mono truncate">{node.method}()</p>
    </div>
  );
}

export function NodePalette() {
  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 bg-gray-900 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 shrink-0">
        <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Node Palette</p>
        <p className="text-[10px] text-gray-600 mt-0.5">Drag onto canvas to add</p>
      </div>

      {/* Scrollable node list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-5">
        {NODE_CATALOGUE.map((category) => {
          const styles = CATEGORY_STYLES[category.category as keyof typeof CATEGORY_STYLES];
          return (
            <div key={category.category}>
              {/* Category header */}
              <div className="flex items-center gap-1.5 mb-2">
                <span className={`w-2 h-2 rounded-full ${styles.dot}`} />
                <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                  {category.category}
                </p>
              </div>

              {/* Node items */}
              <div className="space-y-1.5">
                {category.nodes.map((node) => (
                  <PaletteItem
                    key={node.subtype}
                    node={node}
                    nodeType={category.nodeType}
                    styles={styles}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

'use client';

import { createContext, useContext } from 'react';

type CmdHoverValue = {
  cmdHeld: boolean;
  setHandle: (h: string | undefined) => void;
};

export const CmdHoverContext = createContext<CmdHoverValue>({
  cmdHeld: false,
  setHandle: () => {},
});
export const useCmdHover = () => useContext(CmdHoverContext);

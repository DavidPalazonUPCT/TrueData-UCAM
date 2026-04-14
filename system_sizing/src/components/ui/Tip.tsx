interface TipProps {
  children: React.ReactNode;
  text: string;
}

export function Tip({ children, text }: TipProps) {
  return (
    <span className="relative group/tip cursor-help">
      {children}
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1.5 rounded-md bg-text text-surface text-[10px] leading-snug font-normal normal-case tracking-normal w-max max-w-[220px] opacity-0 group-hover/tip:opacity-100 pointer-events-none transition-opacity duration-150 z-30 shadow-lg text-center">
        {text}
      </span>
    </span>
  );
}

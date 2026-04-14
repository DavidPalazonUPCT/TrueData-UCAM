import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface LatexProps {
  math: string;
  display?: boolean;
  className?: string;
}

export function Latex({ math, display = false, className = "" }: LatexProps) {
  const html = useMemo(
    () => katex.renderToString(math, { displayMode: display, throwOnError: false }),
    [math, display],
  );
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

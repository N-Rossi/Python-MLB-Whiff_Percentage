import { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

const Label = forwardRef(({ className, ...props }, ref) => (
  <label
    ref={ref}
    className={cn(
      "text-xs font-medium uppercase tracking-wider text-muted-foreground",
      className
    )}
    {...props}
  />
));
Label.displayName = "Label";

export { Label };

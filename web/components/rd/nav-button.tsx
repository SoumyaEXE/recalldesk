import Link from "next/link";
import type { ComponentProps, ComponentType, ReactNode } from "react";
import { buttonStyles } from "@/components/base/buttons/button";
import { cx } from "@/utils/cx";

type Icon = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;

/** BoardUI Button styling on a Next.js <Link> (client-side navigation, valid HTML). */
export function NavButton({
  href,
  variant = "primary",
  size = "medium",
  leadingIcon: Leading,
  trailingIcon: Trailing,
  children,
  className,
  ...props
}: Omit<ComponentProps<typeof Link>, "children"> & {
  variant?: keyof typeof buttonStyles.variant;
  size?: keyof typeof buttonStyles.size;
  leadingIcon?: Icon;
  trailingIcon?: Icon;
  children?: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cx(buttonStyles.base, buttonStyles.size[size], buttonStyles.variant[variant], className)}
      {...props}
    >
      {Leading && <Leading className={buttonStyles.icon[size]} aria-hidden />}
      {children != null && <span className={buttonStyles.label[size]}>{children}</span>}
      {Trailing && <Trailing className={buttonStyles.icon[size]} aria-hidden />}
    </Link>
  );
}

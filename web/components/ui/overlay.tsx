"use client";

import type { ReactNode } from "react";
import { Dialog as AriaDialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { CloseButton } from "@/components/base/buttons/close-button";
import { cx } from "@/utils/cx";

/**
 * Side drawer (detail views). React Aria handles focus trap, Escape, outside
 * press and scroll lock; the slide uses the .rd-drawer entering/exiting
 * keyframes so exit animations finish before unmount.
 */
export function Drawer({
  isOpen,
  onOpenChange,
  title,
  subtitle,
  leading,
  headerActions,
  footer,
  children,
  width = "md",
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  leading?: ReactNode;
  headerActions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  width?: "md" | "lg";
}) {
  return (
    <ModalOverlay isOpen={isOpen} onOpenChange={onOpenChange} isDismissable className="rd-overlay rd-no-print fixed inset-0 z-50 bg-neutral-950/30 backdrop-blur-[2px]">
      <Modal
        className={cx(
          "rd-drawer fixed inset-y-0 end-0 flex w-full flex-col border-s border-line bg-frame shadow-drawer outline-none sm:inset-y-2 sm:end-2 sm:rounded-2xl sm:border",
          width === "lg" ? "sm:w-[min(760px,calc(100vw-16px))]" : "sm:w-[min(600px,calc(100vw-16px))]",
        )}
      >
        <AriaDialog className="flex h-full min-h-0 flex-col outline-none">
          {({ close }) => (
            <>
              <header className="flex items-start gap-3 border-b border-line px-5 py-4">
                {leading}
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <Heading slot="title" className="text-title-3-semibold text-balance text-text-primary">
                    {title}
                  </Heading>
                  {subtitle && <div className="text-body-2-regular text-text-tertiary">{subtitle}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {headerActions}
                  <CloseButton size="sm" aria-label="Close panel" onClick={close} />
                </div>
              </header>
              <div className="rd-scroll min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>
              {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-subtle px-5 py-3 sm:rounded-b-2xl">{footer}</footer>}
            </>
          )}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}

/** Centered dialog (forms: paste items, import CSV). */
export function Dialog({
  isOpen,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg";
}) {
  return (
    <ModalOverlay isOpen={isOpen} onOpenChange={onOpenChange} isDismissable className="rd-overlay rd-no-print fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-neutral-950/35 p-0 backdrop-blur-[2px] sm:items-center sm:p-6">
      <Modal className={cx("rd-dialog w-full rounded-t-2xl border border-line bg-frame shadow-pop outline-none sm:rounded-2xl", size === "lg" ? "sm:max-w-[680px]" : "sm:max-w-[520px]")}>
        <AriaDialog className="flex max-h-[calc(100dvh-48px)] flex-col outline-none">
          {({ close }) => (
            <>
              <header className="flex items-start gap-3 px-5 pt-5 pb-3">
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <Heading slot="title" className="text-title-3-semibold text-text-primary">
                    {title}
                  </Heading>
                  {description && <p className="text-body-2-regular text-text-tertiary">{description}</p>}
                </div>
                <CloseButton size="sm" aria-label="Close dialog" onClick={close} />
              </header>
              <div className="rd-scroll min-h-0 flex-1 overflow-y-auto px-5 pb-5">{children}</div>
              {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-subtle px-5 py-3 sm:rounded-b-2xl">{footer}</footer>}
            </>
          )}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}

import type { Transition, Variants } from 'framer-motion';

export const ease = [0.2, 0.7, 0.2, 1] as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease } },
};

export const staggerContainer = (gap = 0.08, delay = 0): Variants => ({
  hidden: {},
  show:   { transition: { staggerChildren: gap, delayChildren: delay } },
});

export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease } },
  exit:    { opacity: 0, y: -4, transition: { duration: 0.15, ease } },
};

export const spring: Transition = { type: 'spring', stiffness: 280, damping: 30 };

// Drawer/panel trượt từ phải — dùng với AnimatePresence (initial/animate/exit).
export const drawerPanel: Variants = {
  hidden: { x: '100%' },
  show: { x: 0, transition: { duration: 0.28, ease } },
  exit: { x: '100%', transition: { duration: 0.22, ease } },
};

export const drawerBackdrop: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.22, ease } },
  exit: { opacity: 0, transition: { duration: 0.18, ease } },
};

// Đổi tab trong drawer — fade nhẹ cho đỡ giật nội dung.
export const tabFade: Variants = {
  hidden: { opacity: 0, y: 4 },
  show: { opacity: 1, y: 0, transition: { duration: 0.18, ease } },
};
